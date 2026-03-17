"""
Market analytics scraper for Watchpoint.

Sources: WatchCharts, Chrono24 ChronoPulse, Subdial, EveryWatch, WatchSignals API,
WatchAnalytics, Watchy.

Extracts price indices and market sentiment data.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, RSSMixin, Article
from database import store_price_index, store_watch_price
from config import log


class MarketAnalyticsScraper(BaseScraper, RSSMixin):
    """Scrapes market intelligence and price index data."""

    category = "market_analytics"
    display_name = "Market Analytics"

    # Source URLs
    WATCHCHARTS_URL = "https://www.watchcharts.com"
    CHRONO24_CHRONOPULSE_URL = "https://www.chrono24.com/chronopulse.htm"
    SUBDIAL_MARKET_URL = "https://subdial.com/market"
    EVERYWATCH_URL = "https://everywatch.com"
    WATCHSIGNALS_API_URL = "https://watchsignals.com/api/indices"
    WATCHANALYTICS_URL = "https://watchanalytics.io"
    WATCHY_URL = "https://watchy.io"

    def scrape(self) -> list[Article]:
        """Scrape all market analytics sources."""
        articles = []

        # WatchCharts - main index
        articles.extend(self._scrape_watchcharts())
        self.delay()

        # Chrono24 ChronoPulse
        articles.extend(self._scrape_chrono24_chronopulse())
        self.delay()

        # Subdial Market
        articles.extend(self._scrape_subdial())
        self.delay()

        # EveryWatch
        articles.extend(self._scrape_everywatch())
        self.delay()

        # WatchSignals API
        articles.extend(self._scrape_watchsignals_api())
        self.delay()

        # WatchAnalytics
        articles.extend(self._scrape_watchanalytics())
        self.delay()

        # Watchy
        articles.extend(self._scrape_watchy())

        return articles

    def _scrape_watchcharts(self) -> list[Article]:
        """Scrape WatchCharts price index data."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHCHARTS_URL)
            if not soup:
                return articles

            # Look for price index value on page
            # Typically found in a prominent section or JSON data
            index_text = soup.find("div", class_=re.compile("index|price|chart", re.I))
            if index_text:
                title = "WatchCharts Price Index Update"
                summary = index_text.get_text(strip=True)[:500]

                # Try to extract numeric value for storage
                numbers = re.findall(r'\d+\.?\d*', summary)
                if numbers:
                    try:
                        value = float(numbers[0])
                        store_price_index("watchcharts_index", "WatchCharts", value)
                    except (ValueError, IndexError):
                        pass

                articles.append(Article(
                    url=self.WATCHCHARTS_URL,
                    title=title,
                    summary=summary,
                    source_name="WatchCharts",
                    source_category=self.category,
                    priority="P1",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] WatchCharts error: {e}")

        return articles

    def _scrape_chrono24_chronopulse(self) -> list[Article]:
        """Scrape Chrono24 ChronoPulse data."""
        articles = []
        try:
            soup = self.fetch_html(self.CHRONO24_CHRONOPULSE_URL)
            if not soup:
                return articles

            # Look for price pulse/index sections
            pulse_div = soup.find("div", class_=re.compile("pulse|index|sentiment", re.I))
            if pulse_div:
                title = "Chrono24 ChronoPulse — Market Sentiment"
                summary = pulse_div.get_text(strip=True)[:500]

                # Extract numeric indicator if present
                numbers = re.findall(r'\d+\.?\d*', summary)
                if numbers:
                    try:
                        value = float(numbers[0])
                        store_price_index("chrono24_pulse", "Chrono24", value)
                    except (ValueError, IndexError):
                        pass

                articles.append(Article(
                    url=self.CHRONO24_CHRONOPULSE_URL,
                    title=title,
                    summary=summary,
                    source_name="Chrono24",
                    source_category=self.category,
                    priority="P1",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Chrono24 ChronoPulse error: {e}")

        return articles

    def _scrape_subdial(self) -> list[Article]:
        """Scrape Subdial market data."""
        articles = []
        try:
            soup = self.fetch_html(self.SUBDIAL_MARKET_URL)
            if not soup:
                return articles

            # Look for market data sections
            market_sections = soup.find_all("section")
            for section in market_sections[:3]:  # Top 3 sections
                title_elem = section.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = section.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.SUBDIAL_MARKET_URL,
                        title=title or "Subdial Market Report",
                        summary=summary,
                        source_name="Subdial",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Subdial error: {e}")

        return articles

    def _scrape_everywatch(self) -> list[Article]:
        """Scrape EveryWatch analytics."""
        articles = []
        try:
            soup = self.fetch_html(self.EVERYWATCH_URL)
            if not soup:
                return articles

            # Look for insights or analytics sections
            insights = soup.find_all("article")[:3]
            for article_elem in insights:
                title_elem = article_elem.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = article_elem.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.EVERYWATCH_URL,
                        title=title,
                        summary=summary,
                        source_name="EveryWatch",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] EveryWatch error: {e}")

        return articles

    def _scrape_watchsignals_api(self) -> list[Article]:
        """Scrape WatchSignals API data."""
        articles = []
        try:
            data = self.fetch_json(self.WATCHSIGNALS_API_URL)
            if not data:
                return articles

            # Process API response
            if isinstance(data, dict):
                indices = data.get("indices", [])
                for idx in indices[:5]:
                    index_name = idx.get("name", "Market Index")
                    value = idx.get("value")
                    change = idx.get("change_pct")

                    if value:
                        store_price_index(
                            index_name,
                            "WatchSignals",
                            float(value),
                            float(change) if change else None
                        )

                        articles.append(Article(
                            url=self.WATCHSIGNALS_API_URL,
                            title=f"WatchSignals: {index_name}",
                            summary=f"Value: {value}, Change: {change}%" if change else f"Value: {value}",
                            source_name="WatchSignals",
                            source_category=self.category,
                            priority="P1",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] WatchSignals API error: {e}")

        return articles

    def _scrape_watchanalytics(self) -> list[Article]:
        """Scrape WatchAnalytics platform."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHANALYTICS_URL)
            if not soup:
                return articles

            # Look for analytics dashboard elements
            dashboard = soup.find("div", class_=re.compile("dashboard|analytics", re.I))
            if dashboard:
                # Extract key metrics
                metrics = dashboard.find_all("div", class_=re.compile("metric|stat|value", re.I))
                for metric in metrics[:3]:
                    text = metric.get_text(strip=True)
                    if text:
                        articles.append(Article(
                            url=self.WATCHANALYTICS_URL,
                            title="WatchAnalytics Market Metric",
                            summary=text[:500],
                            source_name="WatchAnalytics",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] WatchAnalytics error: {e}")

        return articles

    def _scrape_watchy(self) -> list[Article]:
        """Scrape Watchy platform."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHY_URL)
            if not soup:
                return articles

            # Look for main content sections
            main_content = soup.find("main") or soup.find("div", class_="content")
            if main_content:
                sections = main_content.find_all(["article", "section"])[:3]
                for section in sections:
                    title_elem = section.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = section.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.WATCHY_URL,
                            title=title,
                            summary=summary,
                            source_name="Watchy",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Watchy error: {e}")

        return articles
