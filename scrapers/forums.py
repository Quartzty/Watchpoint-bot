"""
Forums scraper for Watchpoint.

Sources: Reddit r/Watches, r/WatchExchange, r/Rolex (via JSON API),
WatchUSeek, Rolex Forums.

Tracks trending discussions and community insights.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from config import log


class ForumsScraper(BaseScraper):
    """Scrapes watch forums and Reddit communities."""

    category = "forums"
    display_name = "Forums"

    # Reddit subreddits (use old.reddit.com to avoid blocking)
    REDDIT_WATCHES_JSON = "https://old.reddit.com/r/Watches/hot.json?limit=10"
    REDDIT_WATCH_EXCHANGE_JSON = "https://old.reddit.com/r/WatchExchange/hot.json?limit=10"
    REDDIT_ROLEX_JSON = "https://old.reddit.com/r/Rolex/hot.json?limit=10"

    def __init__(self):
        super().__init__()
        # Reddit requires a descriptive User-Agent
        self.client.headers["User-Agent"] = "WatchpointBot/2.0 (market intelligence bot; +https://watchpoint.fr)"

    # Forum URLs
    WATCHUSEEK_URL = "https://www.watchuseek.com"
    ROLEX_FORUMS_URL = "https://www.rolexforums.com"

    def scrape(self) -> list[Article]:
        """Scrape all forum sources."""
        articles = []

        # Reddit r/Watches
        articles.extend(self._scrape_reddit_watches())
        self.delay()

        # Reddit r/WatchExchange
        articles.extend(self._scrape_reddit_watch_exchange())
        self.delay()

        # Reddit r/Rolex
        articles.extend(self._scrape_reddit_rolex())
        self.delay()

        # WatchUSeek Forums
        articles.extend(self._scrape_watchuseek())
        self.delay()

        # Rolex Forums
        articles.extend(self._scrape_rolex_forums())

        return articles

    def _scrape_reddit_watches(self) -> list[Article]:
        """Scrape Reddit r/Watches hot posts."""
        articles = []
        try:
            data = self.fetch_json(self.REDDIT_WATCHES_JSON)
            if not data or "data" not in data:
                return articles

            posts = data["data"]["children"][:10]

            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                url = post.get("url", "")
                selftext = post.get("selftext", "")[:500]
                score = post.get("score", 0)
                created_utc = post.get("created_utc")

                # Filter out low-engagement posts
                if score < 50:
                    continue

                summary = selftext or f"Score: {score} upvotes"

                articles.append(Article(
                    url=url,
                    title=title,
                    summary=summary,
                    source_name="Reddit r/Watches",
                    source_category=self.category,
                    priority="P2",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Reddit r/Watches error: {e}")

        return articles

    def _scrape_reddit_watch_exchange(self) -> list[Article]:
        """Scrape Reddit r/WatchExchange hot posts."""
        articles = []
        try:
            data = self.fetch_json(self.REDDIT_WATCH_EXCHANGE_JSON)
            if not data or "data" not in data:
                return articles

            posts = data["data"]["children"][:10]

            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                url = post.get("url", "")
                selftext = post.get("selftext", "")[:300]
                score = post.get("score", 0)

                summary = selftext or f"Activity: {score} engagement points"

                articles.append(Article(
                    url=url,
                    title=title,
                    summary=summary,
                    source_name="Reddit r/WatchExchange",
                    source_category=self.category,
                    priority="P3",  # Secondary market focused
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Reddit r/WatchExchange error: {e}")

        return articles

    def _scrape_reddit_rolex(self) -> list[Article]:
        """Scrape Reddit r/Rolex hot posts."""
        articles = []
        try:
            data = self.fetch_json(self.REDDIT_ROLEX_JSON)
            if not data or "data" not in data:
                return articles

            posts = data["data"]["children"][:10]

            for post_wrapper in posts:
                post = post_wrapper.get("data", {})
                title = post.get("title", "")
                url = post.get("url", "")
                selftext = post.get("selftext", "")[:300]
                score = post.get("score", 0)

                # Filter out low-engagement posts
                if score < 50:
                    continue

                summary = selftext or f"Score: {score} upvotes"

                articles.append(Article(
                    url=url,
                    title=title,
                    summary=summary,
                    source_name="Reddit r/Rolex",
                    source_category=self.category,
                    priority="P2",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Reddit r/Rolex error: {e}")

        return articles

    def _scrape_watchuseek(self) -> list[Article]:
        """Scrape WatchUSeek Forums."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHUSEEK_URL)
            if not soup:
                return articles

            # Look for recent threads or discussions
            thread_section = soup.find("section", class_=re.compile("forum|thread|discussion", re.I))
            if not thread_section:
                # Fallback to main content
                thread_section = soup.find("main") or soup

            if thread_section:
                threads = thread_section.find_all(["article", "div"], class_=re.compile("thread|post|topic", re.I))[:10]

                for thread in threads:
                    title_elem = thread.find(["h2", "h3", "a"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = thread.get_text(strip=True)[:300]

                        # Try to extract thread URL
                        link_elem = thread.find("a", href=True)
                        thread_url = link_elem["href"] if link_elem else self.WATCHUSEEK_URL

                        if thread_url.startswith("/"):
                            from urllib.parse import urljoin
                            thread_url = urljoin(self.WATCHUSEEK_URL, thread_url)

                        articles.append(Article(
                            url=thread_url,
                            title=title,
                            summary=summary,
                            source_name="WatchUSeek Forums",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] WatchUSeek error: {e}")

        return articles

    def _scrape_rolex_forums(self) -> list[Article]:
        """Scrape Rolex Forums."""
        articles = []
        try:
            soup = self.fetch_html(self.ROLEX_FORUMS_URL)
            if not soup:
                return articles

            # Look for recent threads or hot discussions
            main_content = soup.find("main") or soup.find("div", class_=re.compile("content|forum", re.I))
            if main_content:
                threads = main_content.find_all(["article", "div"], class_=re.compile("thread|post|topic", re.I))[:10]

                for thread in threads:
                    title_elem = thread.find(["h2", "h3", "a"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = thread.get_text(strip=True)[:300]

                        # Try to extract thread URL
                        link_elem = thread.find("a", href=True)
                        thread_url = link_elem["href"] if link_elem else self.ROLEX_FORUMS_URL

                        if thread_url.startswith("/"):
                            from urllib.parse import urljoin
                            thread_url = urljoin(self.ROLEX_FORUMS_URL, thread_url)

                        articles.append(Article(
                            url=thread_url,
                            title=title,
                            summary=summary,
                            source_name="Rolex Forums",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Rolex Forums error: {e}")

        return articles
