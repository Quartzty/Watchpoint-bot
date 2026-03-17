"""
Events scraper for Watchpoint.

Sources: Watches & Wonders, Geneva Watch Days, GPHG.

Tracks event announcements, schedules, and coverage.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from config import log


class EventsScraper(BaseScraper):
    """Scrapes watch industry events and major exhibitions."""

    category = "events"
    display_name = "Events"

    # Event source URLs
    WATCHES_WONDERS_URL = "https://www.watchesandwonders.com"
    GENEVA_WATCH_DAYS_URL = "https://www.genevawatchdays.com"  # Best guess for domain
    GPHG_URL = "https://www.gphg.org"

    def scrape(self) -> list[Article]:
        """Scrape all watch industry events."""
        articles = []

        # Watches & Wonders
        articles.extend(self._scrape_watches_wonders())
        self.delay()

        # Geneva Watch Days
        articles.extend(self._scrape_geneva_watch_days())
        self.delay()

        # GPHG (Grand Prix d'Horlogerie de Genève)
        articles.extend(self._scrape_gphg())

        return articles

    def _scrape_watches_wonders(self) -> list[Article]:
        """Scrape Watches & Wonders event data."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHES_WONDERS_URL)
            if not soup:
                return articles

            # Look for event announcements, schedule, or news
            event_section = soup.find(
                "section",
                class_=re.compile("event|announcement|schedule|news", re.I)
            )

            if event_section:
                items = event_section.find_all(["article", "div"], class_=re.compile("item|entry", re.I))[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Look for date info
                        date_elem = item.find(re.compile("date|time|when", re.I))
                        if date_elem:
                            date_str = date_elem.get_text(strip=True)
                            summary = f"Date: {date_str} - {summary}"

                        articles.append(Article(
                            url=self.WATCHES_WONDERS_URL,
                            title=title,
                            summary=summary,
                            source_name="Watches & Wonders",
                            source_category=self.category,
                            priority="P1",
                        ))

                # Fallback if no items found with classes
                if not items:
                    sections = event_section.find_all(["section", "div"])[:3]
                    for section in sections:
                        text = section.get_text(strip=True)
                        if text and len(text) > 50:
                            articles.append(Article(
                                url=self.WATCHES_WONDERS_URL,
                                title="Watches & Wonders Event Update",
                                summary=text[:500],
                                source_name="Watches & Wonders",
                                source_category=self.category,
                                priority="P1",
                            ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Watches & Wonders error: {e}")

        return articles

    def _scrape_geneva_watch_days(self) -> list[Article]:
        """Scrape Geneva Watch Days event data."""
        articles = []
        try:
            soup = self.fetch_html(self.GENEVA_WATCH_DAYS_URL)
            if not soup:
                return articles

            # Look for news, schedule, or event information
            main_content = soup.find("main") or soup.find("div", class_=re.compile("content|main", re.I))
            if main_content:
                sections = main_content.find_all("section")[:5]

                for section in sections:
                    title_elem = section.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = section.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.GENEVA_WATCH_DAYS_URL,
                            title=title or "Geneva Watch Days",
                            summary=summary,
                            source_name="Geneva Watch Days",
                            source_category=self.category,
                            priority="P1",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Geneva Watch Days error: {e}")

        return articles

    def _scrape_gphg(self) -> list[Article]:
        """Scrape GPHG (Grand Prix d'Horlogerie de Genève) data."""
        articles = []
        try:
            soup = self.fetch_html(self.GPHG_URL)
            if not soup:
                return articles

            # Look for award announcements, finalists, or event news
            awards_section = soup.find(
                "section",
                class_=re.compile("award|finalist|competition|news", re.I)
            )

            items = []
            if awards_section:
                items = awards_section.find_all(["article", "div"])[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.GPHG_URL,
                            title=title or "GPHG Award",
                            summary=summary,
                            source_name="GPHG",
                            source_category=self.category,
                            priority="P1",
                        ))

            # Fallback to main content
            if not items:
                main = soup.find("main") or soup
                sections = main.find_all(["section", "article"])[:5]
                for section in sections:
                    text = section.get_text(strip=True)
                    if text and len(text) > 50:
                        articles.append(Article(
                            url=self.GPHG_URL,
                            title="GPHG News",
                            summary=text[:500],
                            source_name="GPHG",
                            source_category=self.category,
                            priority="P1",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] GPHG error: {e}")

        return articles
