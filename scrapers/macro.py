"""
Macro economic indicators scraper for Watchpoint.

Sources: FRED API (interest rates), World Gold Council, XE currency,
Trading Economics.

Tracks CHF/EUR, CHF/USD, gold price, Fed funds rate, and other macro indicators
relevant to the watch market.
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

    # API and source URLs
    FRED_API_URL = "https://api.stlouisfed.org/fred"  # Base URL, requires API key
    WORLD_GOLD_COUNCIL_URL = "https://www.gold.org"
    XE_CURRENCY_URL = "https://www.xe.com"
    TRADING_ECONOMICS_URL = "https://tradingeconomics.com"

    def scrape(self) -> list[Article]:
        """Scrape all macro indicator sources."""
        articles = []

        # FRED API - Interest rates
        articles.extend(self._scrape_fred_indicators())
        self.delay()

        # World Gold Council
        articles.extend(self._scrape_world_gold_council())
        self.delay()

        # XE Currency
        articles.extend(self._scrape_xe_currency())
        self.delay()

        # Trading Economics
        articles.extend(self._scrape_trading_economics())

        return articles

    def _scrape_fred_indicators(self) -> list[Article]:
        """Scrape FRED API for economic indicators."""
        articles = []
        try:
            # Note: FRED API requires authentication. This is a template.
            # In production, you would need to set up API key in environment.
            # For now, we scrape the web page instead.

            soup = self.fetch_html("https://fred.stlouisfed.org")
            if not soup:
                return articles

            # Look for featured economic data
            featured = soup.find("section", class_=re.compile("featured|data|indicator", re.I))
            if featured:
                items = featured.find_all("div", class_=re.compile("item|series|indicator", re.I))[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Try to extract numeric values
                        numbers = re.findall(r'[-+]?\d+\.?\d*%?', summary)
                        if numbers:
                            try:
                                # Store the first numeric value found
                                value = float(numbers[0].rstrip('%'))
                                # Map common FRED indicators
                                index_name = title.lower().replace(" ", "_")[:50]
                                store_price_index(index_name, "FRED", value)
                            except (ValueError, IndexError):
                                pass

                        articles.append(Article(
                            url="https://fred.stlouisfed.org",
                            title=title or "FRED Economic Indicator",
                            summary=summary,
                            source_name="FRED (St. Louis Fed)",
                            source_category=self.category,
                            priority="P1",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] FRED error: {e}")

        return articles

    def _scrape_world_gold_council(self) -> list[Article]:
        """Scrape World Gold Council for gold price and insights."""
        articles = []
        try:
            soup = self.fetch_html(self.WORLD_GOLD_COUNCIL_URL)
            if not soup:
                return articles

            # Look for news, research, or price sections
            news_section = soup.find("section", class_=re.compile("news|research|price", re.I))
            if not news_section:
                news_section = soup.find("main") or soup

            if news_section:
                items = news_section.find_all(["article", "div"], class_=re.compile("item|post|entry", re.I))[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Try to extract gold price if mentioned
                        price_match = re.search(r'\$(\d+[.,]\d+)', summary)
                        if price_match:
                            try:
                                price = float(price_match.group(1).replace(",", ""))
                                store_price_index("gold_price_usd", "World Gold Council", price)
                                summary = f"Gold: ${price}/oz - {summary}"
                            except ValueError:
                                pass

                        articles.append(Article(
                            url=self.WORLD_GOLD_COUNCIL_URL,
                            title=title or "Gold Market Update",
                            summary=summary,
                            source_name="World Gold Council",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] World Gold Council error: {e}")

        return articles

    def _scrape_xe_currency(self) -> list[Article]:
        """Scrape XE for currency exchange rates."""
        articles = []
        try:
            soup = self.fetch_html(self.XE_CURRENCY_URL)
            if not soup:
                return articles

            # Look for currency rate sections
            rates_section = soup.find("section", class_=re.compile("rate|currency|exchange", re.I))
            if not rates_section:
                rates_section = soup.find("main") or soup

            if rates_section:
                # Look for CHF pairs (most relevant for watch market)
                chf_content = rates_section.get_text(strip=True)

                # Extract rates for CHF/USD and CHF/EUR if present
                chf_usd_match = re.search(r'CHF.*?USD.*?([\d.]+)', chf_content)
                chf_eur_match = re.search(r'CHF.*?EUR.*?([\d.]+)', chf_content)

                rates_info = ""
                if chf_usd_match:
                    try:
                        rate = float(chf_usd_match.group(1))
                        store_price_index("chf_usd", "XE", rate)
                        rates_info += f"CHF/USD: {rate} "
                    except ValueError:
                        pass

                if chf_eur_match:
                    try:
                        rate = float(chf_eur_match.group(1))
                        store_price_index("chf_eur", "XE", rate)
                        rates_info += f"CHF/EUR: {rate}"
                    except ValueError:
                        pass

                if rates_info:
                    articles.append(Article(
                        url=self.XE_CURRENCY_URL,
                        title="Currency Exchange Rates - CHF Focus",
                        summary=rates_info,
                        source_name="XE Currency",
                        source_category=self.category,
                        priority="P2",
                    ))

                # Generic rates article
                summary = chf_content[:500]
                articles.append(Article(
                    url=self.XE_CURRENCY_URL,
                    title="Currency Market",
                    summary=summary,
                    source_name="XE Currency",
                    source_category=self.category,
                    priority="P3",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] XE Currency error: {e}")

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
