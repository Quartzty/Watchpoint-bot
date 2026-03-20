"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — CONTENT GENERATION           ║
╚══════════════════════════════════════════════════════════╝

Picks categories via weighted rotation, builds prompts from
scraped data, calls Claude, applies quality filters.
Returns (text, image_urls, msg_type, category).
"""

import re
import random
import anthropic
from datetime import datetime, timedelta
from config import (
    ANTHROPIC_KEY, TIMEZONE, MODEL_FLASH, MODEL_RICH,
    SHORT_CATEGORIES, RICH_CATEGORIES, RICH_WEIGHTS, log,
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
    """Pick a category using weighted rotation that avoids repeating recent choices."""
    if slot_type == "short":
        return random.choice(SHORT_CATEGORIES)

    # Rich: weighted rotation with recency penalty
    recent = get_recent_categories(days=3)
    recent_cats = [r["category"] for r in recent]

    weights = {}
    for cat, base_weight in RICH_WEIGHTS.items():
        count = recent_cats.count(cat)
        penalty = max(0.5, base_weight * (0.5 ** count))
        weights[cat] = penalty

    categories = list(weights.keys())
    w = [weights[c] for c in categories]
    total = sum(w)
    w = [x / total for x in w]

    chosen = random.choices(categories, weights=w, k=1)[0]
    log.info(f"Category selection: {chosen} (weights: {weights})")
    return chosen


# ─── QUALITY FILTERS ─────────────────────────────────────────────────────────

_META_PHRASES = [
    "ma plage de dates", "plage de dates autorisée",
    "hors de ma plage", "hors de la plage autorisée",
    "après avoir effectué plusieurs recherches",
    "en cherchant les actualités récentes",
    "conformément à mes instructions",
    "je ne peux pas produire", "je suis incapable de",
    "il m'est impossible de",
    "je n'ai trouvé aucune actualité horlogère",
    "aucune actualité horlogère valide",
    "dans la plage de dates",
    "je n'ai pas trouvé", "mes recherches n'ont",
    "aucun résultat pertinent",
    "malheureusement", "je n'ai pas pu",
    "il semble qu'aucune", "aucune information récente",
    "je ne dispose pas", "les sources disponibles",
    "il m'est difficile de", "je manque de données",
    "mes capacités ne me permettent", "en tant qu'assistant",
    "en tant qu'ia", "je suis un modèle",
    "mes connaissances s'arrêtent", "au-delà de mes capacités",
]

_IA_WARNING_PHRASES = [
    "témoigne de l'excellence", "dans un contexte de marché en mutation",
    "un signal fort que", "cette pièce incarne",
    "illustre parfaitement", "vient confirmer la tendance",
    "s'inscrit dans une dynamique", "démontre une fois de plus",
    "constitue un tournant", "marque un jalon",
    "force est de constater", "il convient de noter",
    "il est intéressant de noter", "il est à noter que",
    "sans surprise", "comme on pouvait s'y attendre",
]


# ─── LENGTH ENFORCEMENT ─────────────────────────────────────────────────────

# Max chars per slot type
_MAX_CHARS_SHORT = 500
_MAX_CHARS_RICH = 1400


def is_too_long(text: str, slot_type: str) -> bool:
    """Check if a message exceeds character limits."""
    limit = _MAX_CHARS_SHORT if slot_type == "short" else _MAX_CHARS_RICH
    # Count chars excluding HTML tags
    plain = re.sub(r"<[^>]+>", "", text)
    return len(plain) > limit


def truncate_message(text: str, slot_type: str) -> str:
    """Truncate message to character limit, cutting at last sentence boundary."""
    limit = _MAX_CHARS_SHORT if slot_type == "short" else _MAX_CHARS_RICH
    plain = re.sub(r"<[^>]+>", "", text)
    if len(plain) <= limit:
        return text

    # Find last sentence end before limit
    truncated = plain[:limit]
    last_period = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_period > limit * 0.5:
        # Rebuild from original text up to that point
        # Count plain chars to find corresponding position in HTML text
        plain_count = 0
        html_pos = 0
        target = last_period + 1
        in_tag = False
        for i, ch in enumerate(text):
            if ch == "<":
                in_tag = True
            elif ch == ">":
                in_tag = False
                html_pos = i + 1
                continue
            if not in_tag:
                plain_count += 1
                if plain_count >= target:
                    html_pos = i + 1
                    break

        text = text[:html_pos].rstrip()

    log.warning(f"Message truncated: {len(plain)} -> ~{limit} chars")
    return text


def is_meta_commentary(text: str) -> bool:
    """Block messages where Claude talks about its own process."""
    t = text.lower()
    return any(phrase in t for phrase in _META_PHRASES)


def check_ia_warning(text: str) -> list:
    """Check for soft IA markers (logged but not blocked)."""
    t = text.lower()
    found = [p for p in _IA_WARNING_PHRASES if p in t]
    if found:
        log.warning(f"IA warning phrases detected: {found}")
    return found


def is_skip_response(text: str) -> bool:
    """Check if Claude returned SKIP (no suitable content found)."""
    plain = re.sub(r"<[^>]+>", "", text).strip()
    return plain.upper() == "SKIP"


def parse_images_from_response(raw: str) -> tuple:
    """Extract IMAGE: URLs from response. Returns (text, list_of_image_urls)."""
    lines = raw.split("\n")
    image_urls = []
    text_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("IMAGE:"):
            url = stripped.replace("IMAGE:", "").strip()
            if url.startswith("http"):
                image_urls.append(url)
        else:
            text_lines.append(line)

    text = "\n".join(text_lines).strip()
    return text, image_urls


# ─── PROMPT BUILDING ─────────────────────────────────────────────────────────

def _format_articles_for_prompt(articles: list, max_items: int = 8) -> str:
    """Format scraped articles into a readable block for Claude, including image URLs."""
    if not articles:
        return "(Aucun article récent disponible)"

    lines = []
    for a in articles[:max_items]:
        line = f"- [{a['source_name']}] {a['title']}"
        if a.get("summary"):
            line += f"\n  {a['summary'][:200]}"
        if a.get("url"):
            line += f"\n  URL: {a['url']}"
        if a.get("image_url"):
            line += f"\n  IMAGE: {a['image_url']}"
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


def _collect_article_images(articles: list) -> list:
    """Collect image URLs from scraped articles."""
    images = []
    for a in articles:
        if a.get("image_url") and a["image_url"].startswith("http"):
            images.append(a["image_url"])
    return images


# ─── CONTENT GENERATION ──────────────────────────────────────────────────────

# Map source categories to scraper category names
_CATEGORY_TO_SOURCE = {
    "news_flash":      ["watch_media", "events", "forums"],
    "market_signal":   ["market_analytics", "secondary_market"],
    "event_flash":     ["auctions", "events"],
    "release_flash":   ["watch_media"],
    "release":         ["watch_media"],
    "discontinuation": ["watch_media", "forums", "secondary_market"],
    "market_update":   ["market_analytics", "secondary_market"],
    "analysis":        ["industry_research", "macro_indicators"],
    "event":           ["auctions", "events"],
}


def generate_message(slot: int, slot_type: str, max_retries: int = 2) -> list:
    """Generate message(s) for a slot with retry logic.
    Returns list of (text, image_urls, msg_type, category)."""
    for attempt in range(max_retries):
        result = _try_generate(slot, slot_type)
        if result:
            return result
        if attempt < max_retries - 1:
            log.warning(f"Attempt {attempt + 1} failed for slot {slot} — retrying with new category")
    return []


def generate_specific(cat_key: str) -> list:
    """Generate a message for a specific category (for testing)."""
    category = CATEGORIES.get(cat_key)
    if not category:
        log.error(f"Unknown category: {cat_key}")
        return []
    slot_type = category["slot_type"]
    return _try_generate(slot=99, slot_type=slot_type, force_category=cat_key)


def _try_generate(slot: int, slot_type: str, force_category: str = None) -> list:
    """Single attempt to generate message(s) for a slot."""
    cat_key = force_category or pick_category(slot_type)
    category = CATEGORIES.get(cat_key)

    if not category:
        log.error(f"Unknown category: {cat_key}")
        return []

    msg_type = category["msg_type"]
    is_short = slot_type == "short"

    log.info(f"Generating [{msg_type}] {category['label']} for slot {slot}")

    # ── Gather scraped data for the prompt ───────────────────────────────
    source_cats = _CATEGORY_TO_SOURCE.get(cat_key, [])
    articles = []
    for src_cat in source_cats:
        articles.extend(get_fresh_articles(category=src_cat, hours=48, unused_only=True, limit=5))

    # Sort by priority (P1 first) then recency
    articles.sort(key=lambda a: (a.get("priority", "P3"), a.get("scraped_at", "")))

    # Collect image URLs from scraped articles
    scraped_images = _collect_article_images(articles)

    articles_text = _format_articles_for_prompt(articles)
    indices_text = _format_indices_for_prompt()
    trends_text = _format_price_trends()

    # ── Build the prompt ─────────────────────────────────────────────────
    has_articles = articles and articles_text != "(Aucun article récent disponible)"

    if has_articles:
        prompt_template = category["prompt"]
    else:
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

    # Slot type instructions
    if is_short:
        length_instruction = "LONGUEUR MAX : 350-500 caractères (hors HTML). Court, percutant, un seul sujet."
    else:
        length_instruction = "LONGUEUR MAX : 500-1400 caractères (hors HTML). Détaillé mais concis. Ton humain."

    user_prompt += f"""

Date actuelle : {now_str} — Informations entre le {date_limit} et le {date_today}.
{dedup_block}
{length_instruction}

Si des URLs d'images sont fournies (lignes IMAGE:), inclus la plus pertinente en début de réponse : IMAGE: url

Reponds UNIQUEMENT avec le message Telegram final. Aucun commentaire sur tes recherches."""

    # ── API call ─────────────────────────────────────────────────────────
    model = MODEL_FLASH if is_short else MODEL_RICH
    max_tok = 300 if is_short else 800
    max_srch = 2 if is_short else 4

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

        # Extract text from response
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

        if is_skip_response(raw):
            log.info("Claude returned SKIP — no suitable content")
            return []

        # ── IA warning check (soft — log only) ───────────────────────────
        check_ia_warning(raw)

        # ── Extract images and text ──────────────────────────────────────
        text, claude_images = parse_images_from_response(raw)

        # ── Length enforcement ─────────────────────────────────────────
        if is_too_long(text, slot_type):
            text = truncate_message(text, slot_type)

        # Combine images: Claude's picks first, then scraped images as fallback
        all_images = claude_images.copy()
        for img in scraped_images:
            if img not in all_images:
                all_images.append(img)
        # Keep max 2 images
        image_urls = all_images[:2]

        if image_urls:
            log.info(f"Image URLs: {[u[:60] + '...' for u in image_urls]}")
        else:
            log.info("No image URLs found — message will be text-only")

        log.info(f"Message generated ({msg_type}): {len(text)} chars, {len(image_urls)} images")

        # Record for anti-repetition
        body_lines = [l.strip() for l in text.split("\n") if l.strip()]
        body_start = body_lines[0] if body_lines else ""
        summary = re.sub(r"<[^>]+>", "", body_start)[:120]

        if summary:
            record_sent_message(slot, cat_key, msg_type, summary, success=True)

        return [(text, image_urls, msg_type, cat_key)]

    except anthropic.APIError as e:
        log.error(f"Anthropic API error: {e}")
        log_health_event("api_error", str(e))
        return []
    except Exception as e:
        log.error(f"Unexpected error in generate: {e}")
        log_health_event("generation_error", str(e))
        return []
