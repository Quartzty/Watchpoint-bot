"""
Macro economic indicators scraper for Watchpoint.

Sources: Trading Economics.

Tracks economic indicators relevant to the watch market.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from database import store_price_index
from config import log


class MacroIndicatorsScraper(BaseScraper):
    """Scrapes macroeconomic indicators relevant to watches."""

    category = "macro_indicators"
    display_name = "Macro Indicators"

    # Source URL
    TRADING_ECONOMICS_URL = "https://tradingeconomics.com"

    def scrape(self) -> list[Article]:
        """Scrape all macro indicator sources."""
        articles = []

        # Trading Economics
        articles.extend(self._scrape_trading_economics())

        return articles

    def _scrape_trading_economics(self) -> list[Article]:
        """Scrape Trading Economics for macro data."""
        articles = []
        try:
            soup = self.fetch_html(self.TRADING_ECONOMICS_URL)
            if not soup:
                return articles

            # Look for featured economic indicators
            featured = soup.find("section", class_=re.compile("featured|economic|indicator", re.I))
            if not featured:
                featured = soup.find("main") or soup

            if featured:
                items = featured.find_all(["article", "div"], class_=re.compile("item|card|indicator", re.I))[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Try to extract numeric indicators
                        numbers = re.findall(r'[-+]?\d+\.?\d*%?', summary)
                        if numbers:
                            try:
                                value = float(numbers[0].rstrip('%'))
                                index_name = title.lower().replace(" ", "_")[:50]
                                store_price_index(index_name, "Trading Economics", value)
                            except (ValueError, IndexError):
                                pass

                        articles.append(Article(
                            url=self.TRADING_ECONOMICS_URL,
                            title=title or "Economic Indicator",
                            summary=summary,
                            source_name="Trading Economics",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Trading Economics error: {e}")

        return articles
