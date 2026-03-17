"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — CONTENT GENERATION           ║
╚══════════════════════════════════════════════════════════╝

Picks categories via weighted rotation, builds prompts from
scraped data, calls Claude, applies quality filters.
"""

import re
import random
import anthropic
from datetime import datetime, timedelta
from config import (
    ANTHROPIC_KEY, TIMEZONE, MODEL_FLASH, MODEL_RICH,
    FLASH_CATEGORIES, RICH_CATEGORIES, RICH_WEIGHTS, log,
)
from prompts import SYSTEM_PROMPT, CATEGORIES
from database import (
    get_fresh_articles, get_latest_indices, get_index_history,
    get_recent_topics, get_recent_categories, get_price_trend,
    record_sent_message, log_health_event,
)

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)


# ─── CATEGORY SELECTION ──────────────────────────────────────────────────────

def pick_category(slot_type: str) -> str:
    """Pick a category using weighted rotation that avoids repeating recent choices.

    For flash slots: randomly picks from FLASH_CATEGORIES.
    For rich slots: uses weighted selection that deprioritizes recently used categories.
    """
    if slot_type == "flash":
        return random.choice(FLASH_CATEGORIES)

    # Rich: weighted rotation with recency penalty
    recent = get_recent_categories(days=3)
    recent_cats = [r["category"] for r in recent]

    # Build weight table with recency penalty
    weights = {}
    for cat, base_weight in RICH_WEIGHTS.items():
        # Count how many times this category appeared in last 3 days
        count = recent_cats.count(cat)
        # Reduce weight by 50% for each recent use, minimum 0.5
        penalty = max(0.5, base_weight * (0.5 ** count))
        weights[cat] = penalty

    # Weighted random selection
    categories = list(weights.keys())
    w = [weights[c] for c in categories]
    total = sum(w)
    w = [x / total for x in w]

    chosen = random.choices(categories, weights=w, k=1)[0]
    log.info(f"Category selection: {chosen} (weights: {weights})")
    return chosen


# ─── QUALITY FILTERS ─────────────────────────────────────────────────────────

_META_PHRASES = [
    "ma plage de dates",
    "plage de dates autorisée",
    "hors de ma plage",
    "hors de la plage autorisée",
    "après avoir effectué plusieurs recherches",
    "en cherchant les actualités récentes",
    "conformément à mes instructions",
    "je ne peux pas produire",
    "je suis incapable de",
    "il m'est impossible de",
    "je n'ai trouvé aucune actualité horlogère",
    "aucune actualité horlogère valide",
    "dans la plage de dates",
    "je n'ai pas trouvé",
    "mes recherches n'ont",
    "aucun résultat pertinent",
]


def is_meta_commentary(text: str) -> bool:
    """Block messages where Claude talks about its own process."""
    t = text.lower()
    return any(phrase in t for phrase in _META_PHRASES)


_RELEASE_INDICATORS = [
    "réserve de marche", "reserve de marche",
    "calibre ", "cal.", "mouvement automatique", "mouvement manufacture",
    "analyse watchpoint", "marché secondaire", "marche secondaire",
    "boîtier en", "boitier en", "diamètre mm", "mm de diamètre",
    "tirage limité", "exemplaires",
    "source :", "<i>source",
]


def is_release_disguised_as_flash(text: str, msg_type: str) -> bool:
    """Block detailed release content in flash slots."""
    if msg_type not in ("NEWS", "FLASH"):
        return False
    if len(text) > 420:
        log.warning(f"Flash too long ({len(text)} chars) — probably a release")
        return True
    t = text.lower()
    hits = [ind for ind in _RELEASE_INDICATORS if ind in t]
    if hits:
        log.warning(f"Flash contains release indicators {hits} — blocked")
        return True
    return False


def parse_image(raw: str) -> tuple:
    """Extract IMAGE: URL from first line if present."""
    lines = raw.split("\n")
    if lines[0].strip().startswith("IMAGE:"):
        image_url = lines[0].replace("IMAGE:", "").strip()
        return "\n".join(lines[1:]).lstrip(), image_url
    return raw, None


# ─── PROMPT BUILDING ─────────────────────────────────────────────────────────

def _format_articles_for_prompt(articles: list, max_items: int = 8) -> str:
    """Format scraped articles into a readable block for Claude."""
    if not articles:
        return "(Aucun article récent disponible)"

    lines = []
    for a in articles[:max_items]:
        line = f"- [{a['source_name']}] {a['title']}"
        if a.get("summary"):
            line += f"\n  {a['summary'][:200]}"
        if a.get("url"):
            line += f"\n  URL: {a['url']}"
        lines.append(line)
    return "\n".join(lines)


def _format_indices_for_prompt() -> str:
    """Format latest price indices for the prompt."""
    indices = get_latest_indices()
    if not indices:
        return "(Pas de données d'indices récentes)"

    lines = []
    for idx in indices:
        change = f" ({idx['change_pct']:+.1f}%)" if idx.get("change_pct") else ""
        lines.append(f"- {idx['index_name']} ({idx['source']}): {idx['value']}{change} — {idx['recorded_at']}")
    return "\n".join(lines)


def _format_price_trends() -> str:
    """Format notable price trends for market updates."""
    key_refs = [
        ("116500LN", "Rolex", "Daytona"),
        ("5711/1A", "Patek Philippe", "Nautilus"),
        ("15500ST", "Audemars Piguet", "Royal Oak"),
        ("310.30.42.50.01.002", "Omega", "Speedmaster Pro"),
    ]

    lines = []
    for ref, brand, model in key_refs:
        trend = get_price_trend(ref, days=30)
        if len(trend) >= 2:
            latest = trend[-1]
            oldest = trend[0]
            price_field = "price_eur" if latest.get("price_eur") else "price_usd"
            if latest.get(price_field) and oldest.get(price_field):
                change = ((latest[price_field] - oldest[price_field]) / oldest[price_field]) * 100
                currency = "EUR" if price_field == "price_eur" else "USD"
                lines.append(
                    f"- {brand} {model} ({ref}): {latest[price_field]:,.0f} {currency} "
                    f"({change:+.1f}% sur 30j)"
                )

    return "\n".join(lines) if lines else "(Pas assez de données historiques)"


# ─── CONTENT GENERATION ──────────────────────────────────────────────────────

# Map source categories to scraper category names
_CATEGORY_TO_SOURCE = {
    "news_flash":      ["watch_media", "brand_sources", "events", "forums"],
    "market_signal":   ["market_analytics", "secondary_market"],
    "event_flash":     ["auctions", "events"],
    "release":         ["watch_media", "brand_sources"],
    "discontinuation": ["watch_media", "forums", "secondary_market"],
    "market_update":   ["market_analytics", "secondary_market"],
    "analysis":        ["industry_research", "macro_indicators"],
    "event":           ["auctions", "events"],
}


def generate_message(slot: int, slot_type: str, max_retries: int = 2) -> list:
    """Generate message(s) for a slot with retry logic. Returns list of (text, image_url, msg_type, category)."""
    for attempt in range(max_retries):
        result = _try_generate(slot, slot_type)
        if result:
            return result
        if attempt < max_retries - 1:
            log.warning(f"Attempt {attempt + 1} failed for slot {slot} — retrying with new category")
    return []


def _try_generate(slot: int, slot_type: str) -> list:
    """Single attempt to generate message(s) for a slot."""
    cat_key = pick_category(slot_type)
    category = CATEGORIES.get(cat_key)

    if not category:
        log.error(f"Unknown category: {cat_key}")
        return []

    msg_type = category["msg_type"]
    is_flash = slot_type == "flash"

    log.info(f"Generating [{msg_type}] {category['label']} for slot {slot}")

    # ── Gather scraped data for the prompt ───────────────────────────────
    source_cats = _CATEGORY_TO_SOURCE.get(cat_key, [])
    articles = []
    for src_cat in source_cats:
        articles.extend(get_fresh_articles(category=src_cat, hours=48, unused_only=True, limit=5))

    # Sort by priority (P1 first) then recency
    articles.sort(key=lambda a: (a.get("priority", "P3"), a.get("scraped_at", "")))

    articles_text = _format_articles_for_prompt(articles)
    indices_text = _format_indices_for_prompt()
    trends_text = _format_price_trends()

    # ── Build the prompt ─────────────────────────────────────────────────
    has_articles = articles and articles_text != "(Aucun article récent disponible)"

    if has_articles:
        # Use scraped data prompt
        prompt_template = category["prompt"]
    else:
        # Fallback to web search prompt
        prompt_template = category.get("fallback_prompt", category["prompt"])
        log.info(f"No scraped articles for {cat_key} — falling back to web search")

    # Fill template placeholders
    user_prompt = prompt_template.format(
        articles=articles_text,
        indices=indices_text,
        price_trends=trends_text,
    ) if has_articles else prompt_template

    # ── Add context ──────────────────────────────────────────────────────
    now = datetime.now(TIMEZONE)
    now_str = now.strftime("%A %d %B %Y, %H:%M")
    date_today = now.strftime("%d %B %Y")
    date_limit = (now - timedelta(days=7)).strftime("%d %B %Y")

    # Anti-repetition
    recent_topics = get_recent_topics(days=3)
    dedup_block = ""
    if recent_topics:
        topics_list = "\n".join(f"- {t}" for t in recent_topics)
        dedup_block = f"\nSUJETS DEJA COUVERTS RECEMMENT — ne pas aborder :\n{topics_list}\n"

    # Type label
    TYPE_LABELS = {
        "NEWS":          "TYPE 5 — NEWS FLASH",
        "FLASH":         "TYPE 6 — MARKET SIGNAL" if cat_key == "market_signal" else "TYPE 7 — EVENT FLASH",
        "RELEASE":       "TYPE 1 — RELEASE",
        "MARKET_UPDATE": "TYPE 2 — MARKET UPDATE",
        "ANALYSIS":      "TYPE 3 — ANALYSIS",
        "EVENT":         "TYPE 4 — EVENT",
    }
    type_label = TYPE_LABELS.get(msg_type, "TYPE 5 — NEWS FLASH")

    user_prompt += f"""

Date actuelle : {now_str} — Informations entre le {date_limit} et le {date_today}.
{dedup_block}
FORMAT IMPOSE : {type_label} — aucun autre format n'est acceptable.
{"Longueur : 25 a 60 mots maximum. Message court, direct, humanise. Un seul sujet." if is_flash else "Respecte strictement la structure et la longueur du format indique."}

Reponds UNIQUEMENT avec le message Telegram final, pret a etre publie.
Premiere ligne optionnelle : IMAGE: https://... si image directe disponible.
Aucun commentaire. Aucune explication. Aucune mention de tes recherches."""

    # ── API call ─────────────────────────────────────────────────────────
    model = MODEL_FLASH if is_flash else MODEL_RICH
    max_tok = 220 if is_flash else 850
    max_srch = 2 if is_flash else 4

    # Only use web search if no scraped articles (fallback mode)
    tools = []
    if not has_articles:
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_srch}]

    try:
        kwargs = {
            "model": model,
            "max_tokens": max_tok,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if tools:
            kwargs["tools"] = tools

        response = client.messages.create(**kwargs)
        log.info(f"Model: {model} | max_tokens: {max_tok} | web_search: {bool(tools)}")

        # Extract text from response — handle web_search responses too
        text_parts = []
        for b in response.content:
            if b.type == "text" and hasattr(b, "text"):
                text_parts.append(b.text)
        raw = "".join(text_parts).strip()

        if not raw:
            block_types = [b.type for b in response.content]
            log.warning(f"Empty text from Claude. Content block types: {block_types}")
            log.warning(f"Stop reason: {response.stop_reason}")
            log_health_event("generation_empty", f"Slot {slot}, cat={cat_key}, blocks={block_types}")
            return []

        # ── Quality filters ──────────────────────────────────────────────
        if is_meta_commentary(raw):
            log.error("Meta-commentary detected — message blocked")
            log_health_event("meta_commentary_blocked", f"Slot {slot}, cat={cat_key}")
            return []

        if is_release_disguised_as_flash(raw, msg_type):
            log.error("Release content in flash slot — blocked")
            log_health_event("release_in_flash_blocked", f"Slot {slot}, cat={cat_key}")
            return []

        # ── Format output ────────────────────────────────────────────────
        text, image_url = parse_image(raw)
        header = category.get("header", "")
        if header:
            text = f"<b>{header}</b>\n\n{text}"
        if image_url:
            log.info(f"Image URL: {image_url[:70]}...")
        log.info(f"Message generated ({msg_type}): {len(text)} chars")

        # Record for anti-repetition
        body_lines = [l.strip() for l in text.split("\n") if l.strip()]
        _header_kw = {"FLASH NEWS", "RELEASE", "MARKET UPDATE", "REPORT & ANALYSIS",
                      "EVENT", "DISCONTINUATION", "SIGNAL"}
        body_start = next(
            (l for l in body_lines if not any(kw in l for kw in _header_kw)),
            body_lines[0] if body_lines else ""
        )
        summary = re.sub(r"<[^>]+>", "", body_start)[:120]

        if summary:
            record_sent_message(slot, cat_key, msg_type, summary, success=True)

        return [(text, image_url, msg_type, cat_key)]

    except anthropic.APIError as e:
        log.error(f"Anthropic API error: {e}")
        log_health_event("api_error", str(e))
        return []
    except Exception as e:
        log.error(f"Unexpected error in generate: {e}")
        log_health_event("generation_error", str(e))
        return []
