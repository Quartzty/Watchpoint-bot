"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — ARTICLE PAGES                ║
╚══════════════════════════════════════════════════════════╝

Downloads an article page once and extracts:
- its main text (trafilatura: drops menus, footers, comments; keeps lists and
  tables, where specifications and prices usually are);
- its share image (og:image / twitter:image).

The posts are written and fact-checked from this text, not from the 2-3 lines
of an RSS summary: with only a summary, the model fills the gaps from memory
and mixes up prices and specs of older versions of a watch.
"""

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from bs4 import BeautifulSoup

from config import SOURCE_TEXT_MAX_CHARS, USER_AGENT, log

# Below this, the extraction is a teaser, a paywall notice or a failure.
_MIN_TEXT_CHARS = 300

_TIMEOUT = 20
_MAX_PAGE_BYTES = 3 * 1024 * 1024


@dataclass
class ArticlePage:
    url: str
    text: Optional[str] = None     # main text, None if unavailable
    image: Optional[str] = None    # og:image URL, None if absent


def is_article_url(url: str) -> bool:
    """A real article URL (not a site homepage)."""
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and bool(parts.path.strip("/"))
    except ValueError:
        return False


def page_image_from_html(html: str, base_url: str) -> Optional[str]:
    """The page's share image (og:image / twitter:image), if any."""
    soup = BeautifulSoup(html, "lxml")
    for attrs in ({"property": "og:image:secure_url"}, {"property": "og:image"},
                  {"name": "twitter:image"}, {"name": "twitter:image:src"},
                  {"property": "twitter:image"}):
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content", "").strip():
            return urljoin(base_url, tag["content"].strip())
    return None


def _trim(text: str) -> str:
    """Keep long articles within budget without losing their end: the
    specification box and the price are usually at the bottom."""
    if len(text) <= SOURCE_TEXT_MAX_CHARS:
        return text
    head = int(SOURCE_TEXT_MAX_CHARS * 0.65)
    tail = SOURCE_TEXT_MAX_CHARS - head
    return f"{text[:head]}\n[…]\n{text[-tail:]}"


def extract_text(html: str, url: str = None) -> Optional[str]:
    text = trafilatura.extract(
        html, url=url, include_tables=True, include_comments=False,
        include_images=False, favor_precision=True, deduplicate=True,
    )
    if not text or len(text.strip()) < _MIN_TEXT_CHARS:
        return None
    return _trim(text.strip())


def fetch_article_page(url: str, client: httpx.Client = None) -> ArticlePage:
    """Download an article page and extract its text and share image.
    Never raises: on failure the fields stay None."""
    page = ArticlePage(url=url)
    if not is_article_url(url):
        return page
    own_client = client is None
    if own_client:
        client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True,
                              headers={"User-Agent": USER_AGENT,
                                       "Accept": "text/html,application/xhtml+xml"})
    try:
        r = client.get(url)
        r.raise_for_status()
        if "html" not in r.headers.get("content-type", "html"):
            return page
        html = r.text[:_MAX_PAGE_BYTES]
        page.text = extract_text(html, url)
        page.image = page_image_from_html(html, url)
        log.info(f"Article page: {url[:80]} — "
                 f"{len(page.text) if page.text else 0} chars of text, "
                 f"image: {'yes' if page.image else 'no'}")
    except Exception as e:
        log.info(f"Article page unavailable: {url[:80]} — {e}")
    finally:
        if own_client:
            client.close()
    return page
