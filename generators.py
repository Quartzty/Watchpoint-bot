"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — CONTENT GENERATION           ║
╚══════════════════════════════════════════════════════════╝

Picks categories via weighted rotation, builds prompts from
scraped data, calls Claude, applies quality filters.
Returns (text, image_urls, msg_type, category).
"""

import re
import html
import random
import anthropic
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from config import (
    ANTHROPIC_KEY, TIMEZONE, MODEL_FLASH, MODEL_RICH,
    EFFORT_FLASH, EFFORT_RICH, MAX_TOKENS,
    ARTICLE_MAX_AGE_HOURS, MAX_IMAGES_PER_POST,
    SHORT_CATEGORIES, RICH_CATEGORIES, RICH_WEIGHTS, log,
)
from prompts import SYSTEM_PROMPT, CATEGORIES
from database import (
    get_fresh_articles, get_latest_indices, get_index_history,
    get_recent_topics, get_recent_categories, get_price_trend,
    log_health_event,
)
from images import select_images
from telegram import send_admin

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# Server-side fallback (beta): if the model declines a request in a category
# the API can reroute, it re-runs it on a fallback model within the same call.
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Web search runs a server-side loop; when it hits its iteration limit the
# response stops with "pause_turn" and must be re-sent to finish the turn.
_MAX_PAUSE_RESUMES = 3

# Errors that retrying cannot fix (retired/unknown model, invalid or revoked
# API key): they silence the bot, so they must reach the admin immediately.
_CONFIG_ERRORS = (
    anthropic.NotFoundError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
)

_admin_alerts_sent: set = set()


def _alert_admin_once(kind: str, message: str):
    """Send an admin alert at most once per day for a given kind of problem."""
    key = (datetime.now(TIMEZONE).strftime("%Y-%m-%d"), kind)
    if key in _admin_alerts_sent:
        return
    _admin_alerts_sent.add(key)
    send_admin(f"⚠️ <b>Watchpoint — alerte</b>\n{html.escape(message)}")


def check_models() -> bool:
    """Check at startup that the configured Claude models can be used.
    A retired model or a bad API key otherwise only shows up as silent
    generation failures at the next slot."""
    ok = True
    for model in sorted({MODEL_FLASH, MODEL_RICH}):
        try:
            client.models.retrieve(model)
            log.info(f"Claude model available: {model}")
        except _CONFIG_ERRORS as e:
            ok = False
            log.error(f"Claude model check failed for {model}: {e}")
            log_health_event("api_config_error", f"{model}: {str(e)[:300]}")
            _alert_admin_once(
                type(e).__name__,
                f"Le modèle Claude « {model} » est inutilisable ({type(e).__name__}) : "
                f"aucun message ne pourra être généré. Vérifie MODEL_FLASH / MODEL_RICH "
                f"et ANTHROPIC_API_KEY.",
            )
        except anthropic.APIError as e:
            log.warning(f"Could not verify Claude model {model}: {e}")
    return ok


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


def extract_final_text(content) -> str:
    """Return the text of the final answer.

    Blocks are read by type: the response can contain (empty) thinking blocks,
    web search blocks, and short remarks written before a search
    ("Je vais chercher…") as text blocks. Only the text written after the last
    tool block is the message itself."""
    parts = []
    for block in content:
        if block.type == "text":
            parts.append(block.text)
        elif block.type not in ("thinking", "redacted_thinking"):
            parts = []  # tool use / tool result / fallback: drop earlier text
    return "".join(parts).strip()


# Technical lines Claude puts before the message (removed before sending).
# Upper-case keyword = always metadata; any other case only when the value is
# clearly metadata, so that a real "Sources : …" line in a post is kept.
_META_LINE = re.compile(r"^\s*(?P<key>IMAGE|SOURCES?)\s*:\s*(?P<value>.*?)\s*$", re.I)
_ARTICLE_ID = re.compile(r"\bA(\d{1,2})\b")
_ONLY_IDS = re.compile(r"^[\s\[\],;/&+A\d]*(?:et[\s\[\],;/&+A\d]*)*$")
_HREF = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.I)


def parse_response_meta(raw: str) -> tuple:
    """Split Claude's reply into (message text, image URLs, article ids).

    Metadata lines: "IMAGE: url" and "SOURCES: A2, A5" (article numbers given
    in the prompt)."""
    image_urls, source_ids, text_lines = [], [], []
    for line in raw.split("\n"):
        m = _META_LINE.match(line)
        if m:
            key, value = m.group("key"), m.group("value")
            upper = key.isupper()
            if key.upper() == "IMAGE":
                if value.startswith("http"):
                    image_urls.append(value.split()[0])
                    continue
                if upper:
                    continue  # "IMAGE: aucune" etc.
            else:
                ids = [f"A{n}" for n in _ARTICLE_ID.findall(value)]
                if upper or (ids and _ONLY_IDS.match(value)):
                    source_ids.extend(i for i in ids if i not in source_ids)
                    continue
        text_lines.append(line)
    return "\n".join(text_lines).strip(), image_urls, source_ids


def _same_url(a: str, b: str) -> bool:
    return a.strip().rstrip("/").lower() == b.strip().rstrip("/").lower()


def linked_urls(text: str) -> list:
    """URLs of the links in the message (<a href="…">)."""
    return _HREF.findall(text)


def resolve_used_articles(source_ids: list, id_map: dict, text: str,
                          claude_images: list) -> list:
    """Articles the post is based on: the ids Claude declared (SOURCES:),
    else the articles linked in the text or whose image Claude picked."""
    used = [id_map[i] for i in source_ids if i in id_map]
    if not used:
        links = linked_urls(text)
        for a in id_map.values():
            linked = a.get("url") and any(_same_url(a["url"], u) for u in links)
            picked = a.get("image_url") and a["image_url"] in claude_images
            if linked or picked:
                used.append(a)
    if not used and len(id_map) == 1:
        used = list(id_map.values())
    return used


def _is_article_page(url: str) -> bool:
    """A real article URL (not a site homepage, whose share image is a logo)."""
    try:
        return bool(urlsplit(url).path.strip("/"))
    except ValueError:
        return False


def image_candidates(used: list, id_map: dict, claude_images: list, text: str) -> tuple:
    """(direct image URLs, article pages for og:image) — only for the
    article(s) the post is about, never images of unrelated articles."""
    if not id_map:  # web search mode: Claude's pick (validated later), cited pages
        pages = [u for u in linked_urls(text) if _is_article_page(u)]
        return list(claude_images), pages

    used_images = [a["image_url"] for a in used if a.get("image_url")]
    provided = {a["image_url"] for a in id_map.values() if a.get("image_url")}
    # Claude may only pick among the provided images, and one of the used
    # articles' when those are known.
    picks = [u for u in claude_images if u in provided and (u in used_images or not used)]
    pages = [a["url"] for a in used
             if a.get("url") and a.get("published_at") and _is_article_page(a["url"])]
    return picks + [u for u in used_images if u not in picks], pages


# ─── PROMPT BUILDING ─────────────────────────────────────────────────────────

def _format_articles_for_prompt(articles: list, max_items: int = 8) -> tuple:
    """Format scraped articles for Claude, numbered [A1], [A2]… so that the
    reply says which ones it used. Returns (text, {"A1": article, …})."""
    if not articles:
        return "(Aucun article récent disponible)", {}

    lines, id_map = [], {}
    for n, a in enumerate(articles[:max_items], start=1):
        aid = f"A{n}"
        id_map[aid] = a
        line = f"[{aid}] {a['source_name']} — {a['title']}"
        published = a.get("published_at") or ""
        if published[:4].isdigit():
            line += f" (publié le {published[:10]})"
        if a.get("summary"):
            line += f"\n  {a['summary'][:400]}"
        if a.get("url"):
            line += f"\n  URL: {a['url']}"
        if a.get("image_url"):
            line += f"\n  IMAGE: {a['image_url']}"
        lines.append(line)
    return "\n".join(lines), id_map


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

@dataclass
class Post:
    """A generated message, ready to be dispatched and then recorded."""
    text: str
    image_urls: list
    msg_type: str
    category: str
    slot: int
    summary: str = ""                                   # anti-repetition topic
    article_ids: list = field(default_factory=list)     # articles to mark as used
    images: list = field(default_factory=list)          # ImageInfo of image_urls

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
    """Generate message(s) for a slot with retry logic. Returns a list of Post."""
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


def _call_claude(model: str, effort: str, user_prompt: str, tools: list):
    """Call Claude, resuming the turn if the server-side web search pauses."""
    messages = [{"role": "user", "content": user_prompt}]
    kwargs = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "output_config": {"effort": effort},
        "betas": [_FALLBACK_BETA],
        "fallbacks": "default",
    }
    if tools:
        kwargs["tools"] = tools

    response = client.beta.messages.create(messages=messages, **kwargs)
    for _ in range(_MAX_PAUSE_RESUMES):
        if response.stop_reason != "pause_turn":
            break
        log.info("Web search paused (pause_turn) — resuming the turn")
        # Re-send the paused turn as is; the API resumes where it stopped.
        messages = messages + [{"role": "assistant", "content": response.content}]
        response = client.beta.messages.create(messages=messages, **kwargs)
    return response


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
        articles.extend(get_fresh_articles(category=src_cat, hours=48, unused_only=True,
                                           limit=5, max_age_hours=ARTICLE_MAX_AGE_HOURS))

    # P1 first, then the most recent first (publication date when known)
    articles.sort(key=lambda a: a.get("published_at") or a.get("scraped_at") or "", reverse=True)
    articles.sort(key=lambda a: a.get("priority") or "P3")

    articles_text, id_map = _format_articles_for_prompt(articles)
    indices_text = _format_indices_for_prompt()
    trends_text = _format_price_trends()

    # ── Build the prompt ─────────────────────────────────────────────────
    has_articles = bool(id_map)

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

    # Technical lines before the message (removed before sending): which
    # articles were used (so they are not offered again) and their image.
    if has_articles:
        meta_instruction = """Avant le message, ajoute ces lignes techniques (elles seront retirées avant publication) :
SOURCES: les numéros des articles réellement utilisés (ex. SOURCES: A2 — ou SOURCES: A1, A4)
IMAGE: l'URL IMAGE d'un de ces articles s'il en a une (sinon, pas de ligne IMAGE)"""
    else:
        meta_instruction = """Si tu as l'URL directe d'une image de l'article que tu cites, ajoute avant le message une ligne technique IMAGE: url (elle sera retirée). N'invente jamais d'URL."""

    user_prompt += f"""

Date actuelle : {now_str} — Informations entre le {date_limit} et le {date_today}.
{dedup_block}
{length_instruction}

{meta_instruction}

Hormis ces lignes techniques, réponds UNIQUEMENT avec le message Telegram final. Aucun commentaire sur tes recherches."""

    # ── API call ─────────────────────────────────────────────────────────
    model = MODEL_FLASH if is_short else MODEL_RICH
    effort = EFFORT_FLASH if is_short else EFFORT_RICH
    max_srch = 2 if is_short else 4

    # Only use web search if no scraped articles (fallback mode)
    tools = []
    if not has_articles:
        tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_srch}]

    try:
        response = _call_claude(model, effort, user_prompt, tools)
        log.info(f"Model: {response.model} | effort: {effort} | web_search: {bool(tools)} "
                 f"| stop: {response.stop_reason}")

        # ── Stop reasons: never send a refused or cut-off message ────────
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None)
            log.warning(f"Claude declined the request (category: {category})")
            log_health_event("generation_refusal", f"Slot {slot}, cat={cat_key}, category={category}")
            return []

        if response.stop_reason in ("max_tokens", "pause_turn"):
            log.warning(f"Incomplete response (stop_reason={response.stop_reason}) — not sent")
            log_health_event("generation_incomplete",
                             f"Slot {slot}, cat={cat_key}, stop={response.stop_reason}")
            return []

        raw = extract_final_text(response.content)

        if not raw:
            block_types = [b.type for b in response.content]
            log.warning(f"Empty text from Claude. Content block types: {block_types}")
            log.warning(f"Stop reason: {response.stop_reason}")
            log_health_event("generation_empty", f"Slot {slot}, cat={cat_key}, blocks={block_types}")
            return []

        # ── Split metadata lines (SOURCES:, IMAGE:) from the message ─────
        text, claude_images, source_ids = parse_response_meta(raw)

        # ── Quality filters ──────────────────────────────────────────────
        if is_meta_commentary(text):
            log.error("Meta-commentary detected — message blocked")
            log_health_event("meta_commentary_blocked", f"Slot {slot}, cat={cat_key}")
            return []

        if not text or is_skip_response(text):
            log.info("Claude returned SKIP (or no message) — no suitable content")
            return []

        # ── IA warning check (soft — log only) ───────────────────────────
        check_ia_warning(text)

        # ── Length enforcement ─────────────────────────────────────────
        if is_too_long(text, slot_type):
            text = truncate_message(text, slot_type)

        # ── Which articles the post is about ─────────────────────────────
        used = resolve_used_articles(source_ids, id_map, text, claude_images)
        if has_articles:
            log.info(f"Articles used: {[a['title'][:50] for a in used] or 'unknown'} "
                     f"(declared: {source_ids or 'none'})")

        # ── Images: only from those articles, never already posted ───────
        candidates, pages = image_candidates(used, id_map, claude_images, text)
        images = select_images(candidates, pages, MAX_IMAGES_PER_POST)
        image_urls = [img.url for img in images]

        if image_urls:
            log.info(f"Images: {[u[:60] + '...' for u in image_urls]}")
        else:
            log.info("No usable new image — message will be text-only")

        log.info(f"Message generated ({msg_type}): {len(text)} chars, {len(image_urls)} images")

        # Topic recorded for anti-repetition once the post is actually sent
        body_lines = [l.strip() for l in text.split("\n") if l.strip()]
        body_start = body_lines[0] if body_lines else ""
        summary = re.sub(r"<[^>]+>", "", body_start)[:120]

        return [Post(text=text, image_urls=image_urls, msg_type=msg_type, category=cat_key,
                     slot=slot, summary=summary, article_ids=[a["id"] for a in used],
                     images=images)]

    except _CONFIG_ERRORS as e:
        log.error(f"Anthropic configuration error ({type(e).__name__}): {e}")
        log_health_event("api_config_error", str(e)[:300])
        _alert_admin_once(
            type(e).__name__,
            f"Génération impossible ({type(e).__name__}) avec le modèle « {model} » : "
            f"{str(e)[:300]}",
        )
        return []
    except anthropic.APIError as e:
        log.error(f"Anthropic API error: {e}")
        log_health_event("api_error", str(e))
        return []
    except Exception as e:
        log.error(f"Unexpected error in generate: {e}")
        log_health_event("generation_error", str(e))
        return []
