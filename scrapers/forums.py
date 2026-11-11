"""
Forums scraper for Watchpoint.

Sources: WatchUSeek, Rolex Forums.

Tracks trending discussions and community insights.

Reddit was removed: its .json/.rss endpoints refuse unauthenticated requests
from cloud servers (403), Reddit ends RSS on 13 Nov 2026 and closes its
public API by March 2027 (announced 30 Sep 2026).
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from config import log


class ForumsScraper(BaseScraper):
    """Scrapes watch forums and Reddit communities."""

    category = "forums"
    display_name = "Forums"

    # Forum URLs
    WATCHUSEEK_URL = "https://www.watchuseek.com"
    ROLEX_FORUMS_URL = "https://www.rolexforums.com"

    def scrape(self) -> list[Article]:
        """Scrape all forum sources."""
        articles = []

        # WatchUSeek Forums
        articles.extend(self._scrape_watchuseek())
        self.delay()

        # Rolex Forums
        articles.extend(self._scrape_rolex_forums())

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
