"""
Watch media scraper for Watchpoint.

Sources: Hodinkee, Fratello, Monochrome, Worn & Wound, aBlogtoWatch, SJX,
Revolution, Time+Tide, Watchonista, Watch Collecting Lifestyle.

Uses RSS feeds for content discovery. Every URL below answered 200 from
Railway (production logs, 11/11/2026). WatchPro was removed: it answers
403 / an HTML challenge page to Railway's servers.
"""

from scrapers.base import BaseScraper, RSSMixin, Article
from config import log


class WatchMediaScraper(BaseScraper, RSSMixin):
    """Scrapes watch media publications via RSS feeds."""

    category = "watch_media"
    display_name = "Watch Media"

    # RSS Feed URLs
    RSS_SOURCES = [
        # /feed returned an HTML page ("syntax error"); /articles/rss is the feed
        ("Hodinkee", "https://www.hodinkee.com/articles/rss"),
        ("Fratello Watches", "https://www.fratellowatches.com/feed/"),
        ("Monochrome", "https://monochrome-watches.com/feed/"),
        ("Worn & Wound", "https://wornandwound.com/feed/"),
        ("aBlogtoWatch", "https://www.ablogtowatch.com/feed/"),
        ("SJX Watches", "https://watchesbysjx.com/feed"),
        ("Revolution", "https://revolutionwatch.com/feed/"),
        ("Time+Tide", "https://timeandtidewatches.com/feed/"),
        ("Watchonista", "https://www.watchonista.com/feed/articles/"),
        ("Watch Collecting Lifestyle", "https://www.watchcollectinglifestyle.com/home?format=rss"),
        # "All Watch News" removed: it is an iPhone app re-posting the feeds
        # above (Hodinkee, Monochrome, Fratello…), not a publisher.
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
