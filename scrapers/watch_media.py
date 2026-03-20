"""
Watch media scraper for Watchpoint.

Sources: Hodinkee, WatchPro, Fratello, Monochrome, Worn & Wound, All Watch News.

Uses RSS feeds for content discovery.
"""

from scrapers.base import BaseScraper, RSSMixin, Article
from config import log


class WatchMediaScraper(BaseScraper, RSSMixin):
    """Scrapes watch media publications via RSS feeds."""

    category = "watch_media"
    display_name = "Watch Media"

    # RSS Feed URLs
    RSS_SOURCES = [
        ("Hodinkee", "https://www.hodinkee.com/feed"),
        ("WatchPro", "https://www.watchpro.com/feed/"),
        ("Fratello Watches", "https://www.fratellowatches.com/feed/"),
        ("Monochrome", "https://www.monochrome-watches.com/feed/"),
        ("Worn & Wound", "https://www.wornandwound.com/feed/"),
        ("All Watch News", "https://allwatchnews.com/feed/"),
    ]

    def scrape(self) -> list[Article]:
        """Scrape all watch media RSS feeds."""
        articles = []

        for source_name, rss_url in self.RSS_SOURCES:
            try:
                feed_articles = self.parse_rss(rss_url, source_name, priority="P2")
                articles.extend(feed_articles)
                self.delay()
            except Exception as e:
                log.warning(f"[{self.display_name}] {source_name} RSS error: {e}")

        return articles
