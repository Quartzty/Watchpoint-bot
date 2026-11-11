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
from config import (
    ANTHROPIC_KEY, TIMEZONE, MODEL_FLASH, MODEL_RICH,
    EFFORT_FLASH, EFFORT_RICH, EFFORT_SELECT, EFFORT_CHECK, MAX_TOKENS,
    ARTICLE_MAX_AGE_HOURS, MAX_IMAGES_PER_POST,
    SHORT_CATEGORIES, RICH_CATEGORIES, RICH_WEIGHTS, log,
)
from prompts import SYSTEM_PROMPT, CATEGORIES, CHECK_SYSTEM_PROMPT, CHECK_NO_SOURCE
from articles import fetch_article_page, is_article_url
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

def pick_category(slot_type: str, exclude=()) -> str:
    """Pick a category using weighted rotation that avoids repeating recent
    choices. Categories in `exclude` (already tried for this slot) are skipped."""
    if slot_type == "short":
        options = [c for c in SHORT_CATEGORIES if c not in exclude] or list(SHORT_CATEGORIES)
        return random.choice(options)

    # Rich: weighted rotation with recency penalty
    recent = get_recent_categories(days=3)
    recent_cats = [r["category"] for r in recent]

    weights = {}
    for cat, base_weight in RICH_WEIGHTS.items():
        if cat in exclude:
            continue
        count = recent_cats.count(cat)
        penalty = max(0.5, base_weight * (0.5 ** count))
        weights[cat] = penalty
    if not weights:
        weights = dict(RICH_WEIGHTS)

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
    # lyrical / grandiloquent vocabulary (banned by the style rules)
    "iconique", "intemporel", "légendaire", "mythique", "sublime", "majestueu",
    "écrin", "ode à", "savoir-faire ancestral", "quintessence", "alchimie",
    "noblesse", "rend hommage", "incarne", "témoigne", "s'inscrit dans", "..",
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


def linked_urls(text: str) -> list:
    """URLs of the links in the message (<a href="…">)."""
    return _HREF.findall(text)


def citation_snippets(content) -> dict:
    """{url: (title, [passages])} that Claude cited from its web search
    results — the exact source sentences behind the post."""
    found = {}
    for block in content:
        if block.type != "text":
            continue
        for c in getattr(block, "citations", None) or []:
            cited = getattr(c, "cited_text", None)
            if not cited:
                continue
            url = getattr(c, "url", None) or ""
            title, passages = found.setdefault(url, (getattr(c, "title", None) or url, []))
            if cited not in passages:
                passages.append(cited)
    return found


def image_candidates(selected: list, pages: dict, claude_images: list, web_mode: bool) -> list:
    """Image URLs to try, most relevant first — only from the article(s) the
    post is about: their feed image, then their page's share image. In web
    search mode: the cited pages' share images, then the image Claude found.
    Images of unrelated articles are never candidates."""
    if web_mode:
        urls = [p.image for p in pages.values() if p.image] + list(claude_images)
    else:
        urls = [a["image_url"] for a in selected if a.get("image_url")]
        urls += [pages[a["url"]].image for a in selected
                 if a.get("url") in pages and pages[a["url"]].image]
    seen, out = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


_VERDICT_LINE = re.compile(r"^\s*V[EÉ]RIFICATION\s*:\s*(OK|CORRIG[EÉ])\b", re.I)
_REJECT_LINE = re.compile(r"^\s*REJET\b", re.I)


def parse_check_output(out: str) -> tuple:
    """Fact-check reply -> (verdict, text). verdict: "OK", "CORRIGE",
    "REJET", or None when the reply does not follow the expected format."""
    lines = out.strip().split("\n")
    if not lines[0].strip():
        return None, ""
    if _REJECT_LINE.match(lines[0]):
        return "REJET", ""
    m = _VERDICT_LINE.match(lines[0])
    if not m:
        return None, out.strip()
    verdict = "OK" if m.group(1).upper() == "OK" else "CORRIGE"
    return verdict, "\n".join(lines[1:]).strip()


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
        lines.append(line)
    return "\n".join(lines), id_map


def _format_sources_for_prompt(selected: list, pages: dict, id_map: dict) -> tuple:
    """The chosen article(s) with their full text, for the writing step.
    Returns (text, True if the full text of every article is available)."""
    ids = {a["id"]: aid for aid, a in id_map.items()}
    blocks, complete = [], True
    for a in selected:
        block = f"[{ids.get(a['id'], 'A?')}] {a['source_name']} — {a['title']}"
        published = a.get("published_at") or ""
        if published[:4].isdigit():
            block += f" (publié le {published[:10]})"
        if a.get("url"):
            block += f"\nURL: {a['url']}"
        page = pages.get(a.get("url"))
        if page and page.text:
            block += f"\nTEXTE DE L'ARTICLE :\n{page.text}"
        else:
            complete = False
            block += f"\nRÉSUMÉ (texte complet indisponible) :\n{a.get('summary') or '(aucun)'}"
        blocks.append(block)
    return "\n\n".join(blocks), complete


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


def generate_message(slot: int, slot_type: str, max_retries: int = 3) -> list:
    """Generate message(s) for a slot with retry logic. Returns a list of Post.
    Each retry uses a category not tried yet for this slot."""
    tried = []
    for attempt in range(max_retries):
        cat_key = pick_category(slot_type, exclude=tried)
        tried.append(cat_key)
        result = _try_generate(slot, slot_type, force_category=cat_key)
        if result:
            return result
        if attempt < max_retries - 1:
            log.warning(f"Attempt {attempt + 1} failed for slot {slot} ({cat_key}) "
                        f"— retrying with another category")
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


# ─── WRITING PIPELINE ────────────────────────────────────────────────────────
#   1. Claude picks the article from titles + summaries
#   2. the bot downloads the full text of that article
#   3. Claude writes the post from that text only
#   4. a second pass checks the post against the sources (fact-check)

_SELECTION_INSTRUCTION = """ÉTAPE 1 — SÉLECTION. N'écris pas encore le message.
Choisis l'article le plus pertinent pour ce format, en respectant les règles ci-dessus et en évitant les sujets déjà couverts. Deux articles au maximum, et seulement s'ils traitent exactement du même sujet.
Réponds uniquement par une ligne : SOURCES: A? — ou SKIP si aucun article ne convient."""

_WRITE_FROM_FULL_TEXT = """Rédige le message à partir de ce seul texte. Les chiffres (prix, dimensions, calibre, réserve de marche, étanchéité, tirage) ne peuvent venir que de ce texte et doivent concerner le modèle dont parle l'article, pas une version précédente citée en comparaison.

Réponds UNIQUEMENT avec le message Telegram final, sans aucun commentaire."""

_WRITE_FROM_SUMMARY = """Tu ne disposes que d'un résumé de l'article : n'écris aucun chiffre ni aucune caractéristique qui n'y figure pas.

Réponds UNIQUEMENT avec le message Telegram final, sans aucun commentaire."""

_WRITE_FROM_WEB = """Si tu as l'URL directe d'une image de l'article que tu cites, ajoute avant le message une ligne technique IMAGE: url (elle sera retirée). N'invente jamais d'URL.

Hormis cette ligne technique, réponds UNIQUEMENT avec le message Telegram final. Aucun commentaire sur tes recherches."""


def _context_block(is_short: bool) -> str:
    """Date window, topics already covered, length."""
    now = datetime.now(TIMEZONE)
    now_str = now.strftime("%A %d %B %Y, %H:%M")
    date_today = now.strftime("%d %B %Y")
    date_limit = (now - timedelta(days=7)).strftime("%d %B %Y")

    recent_topics = get_recent_topics(days=3)
    dedup_block = ""
    if recent_topics:
        topics_list = "\n".join(f"- {t}" for t in recent_topics)
        dedup_block = f"\nSUJETS DÉJÀ COUVERTS RÉCEMMENT — ne pas aborder :\n{topics_list}\n"

    if is_short:
        length = "LONGUEUR MAX : 350-500 caractères (hors HTML). Court, un seul sujet, l'essentiel."
    else:
        length = "LONGUEUR MAX : 500-1400 caractères (hors HTML). Détaillé, sans phrase inutile."

    return f"""

Date actuelle : {now_str} — Informations entre le {date_limit} et le {date_today}.
{dedup_block}
{length}"""


def select_articles(prompt: str, id_map: dict, model: str):
    """Step 1: Claude picks the article(s) to write about, from titles and
    summaries. Returns the chosen articles, or None to skip the slot."""
    response = _call_claude(model, EFFORT_SELECT, f"{prompt}\n\n{_SELECTION_INSTRUCTION}", [])
    if response.stop_reason == "refusal":
        log.warning("Article selection declined — slot skipped")
        return None
    raw = extract_final_text(response.content)
    _, _, ids = parse_response_meta(raw)
    selected = [id_map[i] for i in ids if i in id_map][:2]
    if selected:
        return selected
    if "SKIP" in raw.upper():
        return None
    log.warning(f"No article number in the selection reply ({raw[:80]!r}) — using the top article")
    return [next(iter(id_map.values()))]


def _scraped_sources(selected: list, pages: dict, category: dict,
                     indices_text: str, trends_text: str) -> list:
    """Fact-check sources in article mode: the text the post was written from."""
    sources = []
    for a in selected:
        page = pages.get(a.get("url"))
        text = page.text if page and page.text else (a.get("summary") or "")
        if text.strip():
            sources.append((f"{a['source_name']} — {a['title']} — {a.get('url', '')}", text))
    internal = []
    if "{indices}" in category["prompt"] and not indices_text.startswith("(Pas"):
        internal.append(indices_text)
    if "{price_trends}" in category["prompt"] and not trends_text.startswith("(Pas"):
        internal.append(trends_text)
    if internal:
        sources.append(("Données enregistrées par le bot (indices, prix)", "\n".join(internal)))
    return sources


def _web_sources(draft: str, content, pages: dict) -> list:
    """Fact-check sources in web search mode: the pages the post links to
    (downloaded now) and the passages Claude cited from its search."""
    sources = []
    for url in [u for u in linked_urls(draft) if is_article_url(u)][:2]:
        page = pages.get(url) or fetch_article_page(url)
        pages[url] = page
        if page.text:
            sources.append((f"Article cité — {url}", page.text))
    for url, (title, passages) in citation_snippets(content).items():
        sources.append((f"Extraits cités par la recherche — {title} — {url}",
                        "\n".join(f"« {p} »" for p in passages)))
    return sources


def fact_check(draft: str, sources: list, model: str) -> tuple:
    """Step 4: a second call compares the post with its sources and fixes,
    removes or rejects what they do not support (prices, specs attributed to
    the wrong model, figures from memory…), and lyrical phrasing.
    sources: [(label, text)]. Returns (verdict, final text)."""
    if sources:
        body = "SOURCES (font foi) :\n\n" + "\n\n".join(
            f"=== {label} ===\n{text}" for label, text in sources)
    else:
        body = CHECK_NO_SOURCE
    response = client.beta.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=CHECK_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"{body}\n\nPOST À VÉRIFIER :\n{draft}"}],
        output_config={"effort": EFFORT_CHECK},
        betas=[_FALLBACK_BETA],
        fallbacks="default",
    )
    if response.stop_reason in ("refusal", "max_tokens", "pause_turn"):
        log.warning(f"Fact-check incomplete (stop_reason={response.stop_reason})")
        return None, ""
    verdict, text = parse_check_output(extract_final_text(response.content))
    if verdict == "OK":
        text = draft  # nothing to change: keep the draft exactly
    return verdict, text


def _try_generate(slot: int, slot_type: str, force_category: str = None) -> list:
    """Single attempt: pick the article, write from its full text, fact-check."""
    cat_key = force_category or pick_category(slot_type)
    category = CATEGORIES.get(cat_key)

    if not category:
        log.error(f"Unknown category: {cat_key}")
        return []

    msg_type = category["msg_type"]
    is_short = slot_type == "short"

    log.info(f"Generating [{msg_type}] {category['label']} for slot {slot}")

    # ── Gather scraped data ──────────────────────────────────────────────
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
    has_articles = bool(id_map)
    if not has_articles:
        log.info(f"No scraped articles for {cat_key} — falling back to web search")

    context = _context_block(is_short)
    model = MODEL_FLASH if is_short else MODEL_RICH
    effort = EFFORT_FLASH if is_short else EFFORT_RICH
    max_srch = 2 if is_short else 4

    try:
        selected, pages = [], {}
        use_web = not has_articles

        if has_articles:
            fill = {"indices": indices_text, "price_trends": trends_text}
            # ── 1. Pick the article from titles + summaries ─────────────
            selected = select_articles(
                category["prompt"].format(articles=articles_text, **fill) + context, id_map, model)
            if not selected:
                # None of the scraped articles fits this format (e.g. only
                # new watches for a news flash): search the web instead of
                # giving up the slot.
                log.info(f"No suitable scraped article for {cat_key} — falling back to web search")
                selected, use_web = [], True
            else:
                log.info(f"Article chosen: {[a['title'][:60] for a in selected]}")

                # ── 2. Full text of the chosen article(s) ───────────────
                for a in selected:
                    if a.get("url"):
                        pages[a["url"]] = fetch_article_page(a["url"])
                sources_text, complete = _format_sources_for_prompt(selected, pages, id_map)
                if not complete:
                    log.info("Full text unavailable — writing from the summary (no figure beyond it)")
                user_prompt = (category["prompt"].format(articles=sources_text, **fill) + context
                               + "\n\n" + (_WRITE_FROM_FULL_TEXT if complete else _WRITE_FROM_SUMMARY))
                tools = []

        if use_web:
            user_prompt = (category.get("fallback_prompt", category["prompt"]) + context
                           + "\n\n" + _WRITE_FROM_WEB)
            tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": max_srch}]

        # ── 3. Write ─────────────────────────────────────────────────────
        response = _call_claude(model, effort, user_prompt, tools)
        log.info(f"Model: {response.model} | effort: {effort} | web_search: {bool(tools)} "
                 f"| stop: {response.stop_reason}")

        # Never send a refused or cut-off message
        if response.stop_reason == "refusal":
            details = getattr(response, "stop_details", None)
            refusal_category = getattr(details, "category", None)
            log.warning(f"Claude declined the request (category: {refusal_category})")
            log_health_event("generation_refusal",
                             f"Slot {slot}, cat={cat_key}, category={refusal_category}")
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
            log_health_event("generation_empty", f"Slot {slot}, cat={cat_key}, blocks={block_types}")
            return []

        draft, claude_images, _ = parse_response_meta(raw)

        if is_meta_commentary(draft):
            log.error("Meta-commentary detected — message blocked")
            log_health_event("meta_commentary_blocked", f"Slot {slot}, cat={cat_key}")
            return []

        if not draft or is_skip_response(draft):
            log.info("Claude returned SKIP (or no message) — no suitable content")
            return []

        # ── 4. Fact-check against the sources ───────────────────────────
        if use_web:
            sources = _web_sources(draft, response.content, pages)
        else:
            sources = _scraped_sources(selected, pages, category, indices_text, trends_text)

        verdict, text = fact_check(draft, sources, model)
        if verdict is None:
            log.warning("Fact-check unusable — post not sent")
            log_health_event("fact_check_failed", f"Slot {slot}, cat={cat_key}")
            return []
        if verdict == "REJET":
            plain = " ".join(re.sub(r"<[^>]+>", "", draft).split())  # one line for the report
            log.warning(f"Fact-check rejected the post: {plain[:300]!r}")
            log_health_event("fact_check_rejected", f"{cat_key} : {plain[:150]}")
            return []
        if verdict == "CORRIGE":
            log.info(f"Fact-check corrected the post\n  BEFORE: {draft}\n  AFTER:  {text}")
            log_health_event("fact_check_corrected", f"{cat_key}")
        else:
            log.info(f"Fact-check OK ({len(sources)} source(s))")

        text, _, _ = parse_response_meta(text)
        if not text or is_meta_commentary(text) or is_skip_response(text):
            log.warning("Nothing publishable after the fact-check — post not sent")
            log_health_event("fact_check_failed", f"Slot {slot}, cat={cat_key}: empty result")
            return []

        # Soft style check (logged only)
        check_ia_warning(text)

        # Length enforcement
        if is_too_long(text, slot_type):
            text = truncate_message(text, slot_type)

        # ── 5. Images: only from the article(s) used, never already posted ─
        candidates = image_candidates(selected, pages, claude_images, web_mode=use_web)
        max_images = min(MAX_IMAGES_PER_POST, max(1, len(selected)))
        images = select_images(candidates, [], max_images)
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
                     slot=slot, summary=summary, article_ids=[a["id"] for a in selected],
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
