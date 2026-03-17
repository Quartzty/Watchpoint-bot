"""
Brand sources scraper for Watchpoint.

Sources: Rolex, Patek Philippe, Audemars Piguet, Omega, Cartier, Tudor, IWC.

Tracks new releases and press announcements from official brand sources.
"""

import re
from typing import Optional
from scrapers.base import BaseScraper, Article
from config import log


class BrandsScraper(BaseScraper):
    """Scrapes official brand news and press releases."""

    category = "brand_sources"
    display_name = "Brand Sources"

    # Brand source URLs
    ROLEX_URL = "https://www.rolex.com"
    PATEK_PHILIPPE_URL = "https://www.patek.com"
    AUDEMARS_PIGUET_URL = "https://www.audemarspiguet.com"
    OMEGA_URL = "https://www.omegawatches.com"
    CARTIER_URL = "https://www.cartier.com"
    TUDOR_URL = "https://www.tudorwatch.com"
    IWC_URL = "https://www.iwc.com"

    BRANDS = [
        ("Rolex", ROLEX_URL),
        ("Patek Philippe", PATEK_PHILIPPE_URL),
        ("Audemars Piguet", AUDEMARS_PIGUET_URL),
        ("Omega", OMEGA_URL),
        ("Cartier", CARTIER_URL),
        ("Tudor", TUDOR_URL),
        ("IWC", IWC_URL),
    ]

    def scrape(self) -> list[Article]:
        """Scrape all official brand sources."""
        articles = []

        for brand_name, brand_url in self.BRANDS:
            try:
                brand_articles = self._scrape_brand(brand_name, brand_url)
                articles.extend(brand_articles)
                self.delay()
            except Exception as e:
                log.warning(f"[{self.display_name}] {brand_name} error: {e}")

        return articles

    def _scrape_brand(self, brand_name: str, brand_url: str) -> list[Article]:
        """Scrape a single brand's news and releases."""
        articles = []
        try:
            soup = self.fetch_html(brand_url)
            if not soup:
                return articles

            # Look for news, press, or releases section
            news_section = soup.find(
                "section",
                class_=re.compile("news|press|release|article", re.I)
            )

            if not news_section:
                # Fallback: look for any article or news-like elements
                news_section = soup.find("main") or soup.find("div", class_="content")

            if news_section:
                # Get top news/press items
                items = news_section.find_all(
                    ["article", "div"],
                    class_=re.compile("news|item|entry|post", re.I)
                )[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3", "a"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Try to extract URL from link
                        link_elem = item.find("a", href=True)
                        item_url = link_elem["href"] if link_elem else brand_url

                        # Make relative URLs absolute
                        if item_url.startswith("/"):
                            # Extract domain from brand_url
                            from urllib.parse import urljoin
                            item_url = urljoin(brand_url, item_url)

                        articles.append(Article(
                            url=item_url,
                            title=title or f"{brand_name} News",
                            summary=summary,
                            source_name=brand_name,
                            source_category=self.category,
                            priority="P1",  # Brand news is high priority
                        ))

                # If no items found with class, try generic approach
                if not items:
                    sections = news_section.find_all(["section", "div"])[:3]
                    for section in sections:
                        title_elem = section.find(["h2", "h3"])
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            if title and len(title) > 5:  # Filter out empty/junk titles
                                summary = section.get_text(strip=True)[:500]

                                articles.append(Article(
                                    url=brand_url,
                                    title=title,
                                    summary=summary,
                                    source_name=brand_name,
                                    source_category=self.category,
                                    priority="P1",
                                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Error scraping {brand_name}: {e}")

        return articles
