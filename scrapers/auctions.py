"""
Auction scraper for Watchpoint.

Sources: Phillips, Sotheby's, Christie's, Antiquorum, Bonhams.

Tracks upcoming auctions and notable results.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from config import log


class AuctionsScraper(BaseScraper):
    """Scrapes auction house watch sales data."""

    category = "auctions"
    display_name = "Auctions"

    # Source URLs
    PHILLIPS_WATCHES_URL = "https://www.phillips.com/departments/watches"
    SOTHEBYS_WATCHES_URL = "https://www.sothebys.com/en/departments/watches"
    CHRISTIES_WATCHES_URL = "https://www.christies.com/departments/watches"
    ANTIQUORUM_URL = "https://antiquorum.swiss"
    BONHAMS_WATCHES_URL = "https://www.bonhams.com/departments/WAT/"

    def scrape(self) -> list[Article]:
        """Scrape all auction house sources."""
        articles = []

        # Phillips
        articles.extend(self._scrape_phillips())
        self.delay()

        # Sotheby's
        articles.extend(self._scrape_sothebys())
        self.delay()

        # Christie's
        articles.extend(self._scrape_christies())
        self.delay()

        # Antiquorum
        articles.extend(self._scrape_antiquorum())
        self.delay()

        # Bonhams
        articles.extend(self._scrape_bonhams())

        return articles

    def _scrape_phillips(self) -> list[Article]:
        """Scrape Phillips auction data."""
        articles = []
        try:
            soup = self.fetch_html(self.PHILLIPS_WATCHES_URL)
            if not soup:
                return articles

            # Look for upcoming sales or featured auctions
            sales = soup.find_all("div", class_=re.compile("sale|auction|lot", re.I))[:5]

            for sale in sales:
                title_elem = sale.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = sale.get_text(strip=True)[:500]

                    # Extract date if present
                    date_elem = sale.find(re.compile("date|when", re.I))
                    if date_elem:
                        summary = f"Date: {date_elem.get_text(strip=True)} - {summary}"

                    articles.append(Article(
                        url=self.PHILLIPS_WATCHES_URL,
                        title=title or "Phillips Watch Auction",
                        summary=summary,
                        source_name="Phillips",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Phillips error: {e}")

        return articles

    def _scrape_sothebys(self) -> list[Article]:
        """Scrape Sotheby's auction data."""
        articles = []
        try:
            soup = self.fetch_html(self.SOTHEBYS_WATCHES_URL)
            if not soup:
                return articles

            # Look for upcoming auctions
            auctions = soup.find_all("div", class_=re.compile("auction|sale|event", re.I))[:5]

            for auction in auctions:
                title_elem = auction.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = auction.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.SOTHEBYS_WATCHES_URL,
                        title=title or "Sotheby's Watch Auction",
                        summary=summary,
                        source_name="Sotheby's",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Sotheby's error: {e}")

        return articles

    def _scrape_christies(self) -> list[Article]:
        """Scrape Christie's auction data."""
        articles = []
        try:
            soup = self.fetch_html(self.CHRISTIES_WATCHES_URL)
            if not soup:
                return articles

            # Look for upcoming sales
            sales = soup.find_all("div", class_=re.compile("sale|auction|lot", re.I))[:5]

            for sale in sales:
                title_elem = sale.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = sale.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.CHRISTIES_WATCHES_URL,
                        title=title or "Christie's Watch Auction",
                        summary=summary,
                        source_name="Christie's",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Christie's error: {e}")

        return articles

    def _scrape_antiquorum(self) -> list[Article]:
        """Scrape Antiquorum auction data."""
        articles = []
        try:
            soup = self.fetch_html(self.ANTIQUORUM_URL)
            if not soup:
                return articles

            # Look for upcoming auctions and results
            main_content = soup.find("main") or soup.find("div", class_="content")
            if main_content:
                auctions = main_content.find_all("section")[:5]

                for auction in auctions:
                    title_elem = auction.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = auction.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.ANTIQUORUM_URL,
                            title=title,
                            summary=summary,
                            source_name="Antiquorum",
                            source_category=self.category,
                            priority="P1",  # Antiquorum is highly specialized
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Antiquorum error: {e}")

        return articles

    def _scrape_bonhams(self) -> list[Article]:
        """Scrape Bonhams auction data."""
        articles = []
        try:
            soup = self.fetch_html(self.BONHAMS_WATCHES_URL)
            if not soup:
                return articles

            # Look for upcoming auctions
            auctions = soup.find_all("div", class_=re.compile("auction|sale|event", re.I))[:5]

            for auction in auctions:
                title_elem = auction.find(["h2", "h3"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    summary = auction.get_text(strip=True)[:500]

                    articles.append(Article(
                        url=self.BONHAMS_WATCHES_URL,
                        title=title or "Bonhams Watch Auction",
                        summary=summary,
                        source_name="Bonhams",
                        source_category=self.category,
                        priority="P2",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Bonhams error: {e}")

        return articles
