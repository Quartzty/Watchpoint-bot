"""
Secondary market scraper for Watchpoint.

Sources: Bezel, Wristcheck, Kalshi (prediction market).

Extracts listing counts and pricing data from secondary market sellers,
plus macro-relevant prediction market data from Kalshi.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from database import store_watch_price
from config import log


class SecondaryMarketScraper(BaseScraper):
    """Scrapes secondary market watch data."""

    category = "secondary_market"
    display_name = "Secondary Market"

    # Source URLs
    BEZEL_URL = "https://getbezel.com"
    WRISTCHECK_URL = "https://www.wristcheck.com"
    KALSHI_URL = "https://kalshi.com/markets"

    # Kalshi keywords relevant to watch market
    KALSHI_KEYWORDS = [
        "luxury", "watch", "gold", "swiss", "inflation",
        "interest rate", "fed", "economy", "tariff", "trade",
    ]

    def scrape(self) -> list[Article]:
        """Scrape all secondary market sources."""
        articles = []

        # Bezel
        articles.extend(self._scrape_bezel())
        self.delay()

        # Wristcheck
        articles.extend(self._scrape_wristcheck())
        self.delay()

        # Kalshi prediction market
        articles.extend(self._scrape_kalshi())

        return articles

    def _scrape_bezel(self) -> list[Article]:
        """Scrape Bezel marketplace."""
        articles = []
        try:
            soup = self.fetch_html(self.BEZEL_URL)
            if not soup:
                return articles

            # Look for active listings
            listings = soup.find_all("div", class_=re.compile("listing|card|watch", re.I))[:5]

            for listing in listings:
                title_elem = listing.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = listing.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.BEZEL_URL,
                        title=title,
                        summary=summary,
                        source_name="Bezel",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Bezel error: {e}")

        return articles

    def _scrape_wristcheck(self) -> list[Article]:
        """Scrape Wristcheck marketplace."""
        articles = []
        try:
            soup = self.fetch_html(self.WRISTCHECK_URL)
            if not soup:
                return articles

            # Look for listing summaries or activity
            activity = soup.find("div", class_=re.compile("activity|listings|recent", re.I))
            if activity:
                summary = activity.get_text(strip=True)[:500]

                articles.append(Article(
                    url=self.WRISTCHECK_URL,
                    title="Wristcheck Market Activity",
                    summary=summary,
                    source_name="Wristcheck",
                    source_category=self.category,
                    priority="P3",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Wristcheck error: {e}")

        return articles

    def _scrape_kalshi(self) -> list[Article]:
        """Scrape Kalshi prediction market for macro-relevant contracts."""
        articles = []
        try:
            soup = self.fetch_html(self.KALSHI_URL)
            if not soup:
                return articles

            # Look for market cards / contracts
            markets = soup.find_all("div", class_=re.compile("market|card|contract", re.I))[:20]

            for market in markets:
                title_elem = market.find(["h2", "h3", "a"])
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                title_lower = title.lower()

                # Filter for relevant keywords
                if not any(kw in title_lower for kw in self.KALSHI_KEYWORDS):
                    continue

                summary = market.get_text(strip=True)[:500]

                # Try to extract probability / price
                price_match = re.search(r'(\d+)[¢%]', summary)
                prob_text = f" (prob: {price_match.group(0)})" if price_match else ""

                articles.append(Article(
                    url=self.KALSHI_URL,
                    title=f"Kalshi: {title}",
                    summary=f"{summary}{prob_text}",
                    source_name="Kalshi",
                    source_category=self.category,
                    priority="P2",
                ))

        except Exception as e:
            log.warning(f"[{self.display_name}] Kalshi error: {e}")

        return articles
