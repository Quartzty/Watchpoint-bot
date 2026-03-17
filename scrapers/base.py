"""
Base scraper class and mixins for Watchpoint source scraping.

Every scraper inherits from BaseScraper and implements scrape().
It returns a list of Article dicts that get stored in the database.
"""

import time
import hashlib
import httpx
from dataclasses import dataclass, field, asdict
from typing import Optional
from bs4 import BeautifulSoup
from config import SCRAPE_REQUEST_TIMEOUT, SCRAPE_DELAY_BETWEEN, USER_AGENT, log
from database import store_article, store_price_index, store_watch_price


@dataclass
class Article:
    """Standardized article/data item from any source."""
    url: str
    title: str
    summary: str = ""
    source_name: str = ""
    source_category: str = ""
    priority: str = "P2"
    published_at: str = None
    raw_html: str = None
    image_url: str = None

    def to_dict(self) -> dict:
        return asdict(self)

    def store(self) -> bool:
        """Store in database. Returns False if duplicate."""
        return store_article(
            url=self.url,
            title=self.title,
            summary=self.summary,
            source_name=self.source_name,
            source_category=self.source_category,
            priority=self.priority,
            published_at=self.published_at,
            raw_html=self.raw_html,
            image_url=self.image_url,
        )


class BaseScraper:
    """Base class for all Watchpoint scrapers."""

    category: str = ""       # e.g. "watch_media", "market_analytics"
    display_name: str = ""   # e.g. "Watch Media"

    def __init__(self):
        self.client = httpx.Client(
            timeout=SCRAPE_REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            },
            follow_redirects=True,
        )
        self._stats = {"fetched": 0, "new": 0, "errors": 0}

    def scrape(self) -> list[Article]:
        """Override this. Scrape all sources in this category, return Articles."""
        raise NotImplementedError

    def run(self) -> dict:
        """Run the scraper, store results, return stats."""
        self._stats = {"fetched": 0, "new": 0, "errors": 0}
        try:
            articles = self.scrape()
            for article in articles:
                self._stats["fetched"] += 1
                if article.store():
                    self._stats["new"] += 1
        except Exception as e:
            log.error(f"[{self.display_name}] Scraper error: {e}")
            self._stats["errors"] += 1
        return self._stats

    def fetch_html(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return parsed HTML. Returns None on error."""
        try:
            r = self.client.get(url)
            r.raise_for_status()
            return BeautifulSoup(r.text, "lxml")
        except Exception as e:
            log.warning(f"[{self.display_name}] Failed to fetch {url}: {e}")
            self._stats["errors"] += 1
            return None

    def fetch_json(self, url: str) -> Optional[dict]:
        """Fetch a JSON endpoint. Returns None on error."""
        try:
            r = self.client.get(url)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning(f"[{self.display_name}] Failed to fetch JSON {url}: {e}")
            self._stats["errors"] += 1
            return None

    def delay(self):
        """Rate-limit pause between requests."""
        time.sleep(SCRAPE_DELAY_BETWEEN)

    def close(self):
        """Close the HTTP client."""
        self.client.close()


class RSSMixin:
    """Mixin for scrapers that consume RSS/Atom feeds."""

    def parse_rss(self, url: str, source_name: str, priority: str = "P2") -> list[Article]:
        """Parse an RSS feed and return Article objects."""
        import feedparser

        articles = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:  # Last 10 entries
                summary = ""
                image_url = None

                if hasattr(entry, "summary"):
                    # Strip HTML from summary but extract image first
                    soup = BeautifulSoup(entry.summary, "lxml")
                    img = soup.find("img")
                    if img and img.get("src"):
                        image_url = img["src"]
                    summary = soup.get_text(strip=True)[:500]

                # Try media:content (common in RSS feeds)
                if not image_url and hasattr(entry, "media_content"):
                    for media in entry.media_content:
                        if media.get("medium") == "image" or media.get("type", "").startswith("image"):
                            image_url = media.get("url")
                            break

                # Try media:thumbnail
                if not image_url and hasattr(entry, "media_thumbnail"):
                    if entry.media_thumbnail:
                        image_url = entry.media_thumbnail[0].get("url")

                # Try enclosures
                if not image_url and hasattr(entry, "enclosures"):
                    for enc in entry.enclosures:
                        if enc.get("type", "").startswith("image"):
                            image_url = enc.get("href") or enc.get("url")
                            break

                published = None
                if hasattr(entry, "published"):
                    published = entry.published

                articles.append(Article(
                    url=entry.link,
                    title=entry.title,
                    summary=summary,
                    source_name=source_name,
                    source_category=self.category,
                    priority=priority,
                    published_at=published,
                    image_url=image_url,
                ))
        except Exception as e:
            log.warning(f"RSS parse error for {source_name}: {e}")

        return articles
