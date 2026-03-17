"""
Secondary market scraper for Watchpoint.

Sources: Chrono24, eBay Watches, Watchfinder, Bezel, Crown & Caliber,
Wristcheck, Watchbox, Bob's Watches, Hodinkee Shop.

Extracts listing counts and pricing data from secondary market sellers.
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
    CHRONO24_URL = "https://www.chrono24.com"
    EBAY_WATCHES_URL = "https://www.ebay.com/sch/Wristwatches/4657/bn_16565190"
    WATCHFINDER_URL = "https://www.watchfinder.com"
    BEZEL_URL = "https://getbezel.com"
    CROWN_CALIBER_URL = "https://www.crownandcaliber.com"
    WRISTCHECK_URL = "https://www.wristcheck.com"
    WATCHBOX_URL = "https://thewatchbox.com"
    BOBS_WATCHES_URL = "https://www.bobswatches.com"
    HODINKEE_SHOP_URL = "https://shop.hodinkee.com"

    def scrape(self) -> list[Article]:
        """Scrape all secondary market sources."""
        articles = []

        # Chrono24
        articles.extend(self._scrape_chrono24())
        self.delay()

        # eBay Watches
        articles.extend(self._scrape_ebay_watches())
        self.delay()

        # Watchfinder
        articles.extend(self._scrape_watchfinder())
        self.delay()

        # Bezel
        articles.extend(self._scrape_bezel())
        self.delay()

        # Crown & Caliber
        articles.extend(self._scrape_crown_caliber())
        self.delay()

        # Wristcheck
        articles.extend(self._scrape_wristcheck())
        self.delay()

        # Watchbox
        articles.extend(self._scrape_watchbox())
        self.delay()

        # Bob's Watches
        articles.extend(self._scrape_bobs_watches())
        self.delay()

        # Hodinkee Shop
        articles.extend(self._scrape_hodinkee_shop())

        return articles

    def _scrape_chrono24(self) -> list[Article]:
        """Scrape Chrono24 marketplace data."""
        articles = []
        try:
            soup = self.fetch_html(self.CHRONO24_URL)
            if not soup:
                return articles

            # Look for trending watches or market activity
            trending = soup.find("div", class_=re.compile("trending|popular|top", re.I))
            if trending:
                items = trending.find_all("div", class_=re.compile("item|watch|product", re.I))[:5]

                for item in items:
                    title_elem = item.find(["h2", "h3", "a"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = item.get_text(strip=True)[:500]

                        # Try to extract price if present
                        price_text = item.find(re.compile("price|cost", re.I))
                        if price_text:
                            summary = price_text.get_text(strip=True) + " - " + summary

                        articles.append(Article(
                            url=self.CHRONO24_URL,
                            title=title or "Chrono24 Watch Listing",
                            summary=summary,
                            source_name="Chrono24",
                            source_category=self.category,
                            priority="P2",
                        ))

                # Create summary article about listings
                total = trending.get_text(strip=True)
                articles.append(Article(
                    url=self.CHRONO24_URL,
                    title="Chrono24 Market Activity",
                    summary=f"Active listings and trending watches on Chrono24: {total[:200]}",
                    source_name="Chrono24",
                    source_category=self.category,
                    priority="P3",
                ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Chrono24 error: {e}")

        return articles

    def _scrape_ebay_watches(self) -> list[Article]:
        """Scrape eBay watches category."""
        articles = []
        try:
            soup = self.fetch_html(self.EBAY_WATCHES_URL)
            if not soup:
                return articles

            # Look for listing count and hot items
            listing_info = soup.find(re.compile("span|div"), class_=re.compile("results|count|items", re.I))
            if listing_info:
                count_text = listing_info.get_text(strip=True)

                articles.append(Article(
                    url=self.EBAY_WATCHES_URL,
                    title="eBay Wristwatch Listings",
                    summary=count_text[:500],
                    source_name="eBay",
                    source_category=self.category,
                    priority="P3",
                ))

            # Get hot items
            hot_items = soup.find_all("div", class_=re.compile("item", re.I))[:5]
            for item in hot_items:
                title_elem = item.find(["h2", "a"])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    price_elem = item.find(re.compile("price", re.I))
                    price = price_elem.get_text(strip=True) if price_elem else ""

                    articles.append(Article(
                        url=self.EBAY_WATCHES_URL,
                        title=title[:100],
                        summary=f"Price: {price}",
                        source_name="eBay",
                        source_category=self.category,
                        priority="P3",
                    ))
        except Exception as e:
            log.warning(f"[{self.display_name}] eBay error: {e}")

        return articles

    def _scrape_watchfinder(self) -> list[Article]:
        """Scrape Watchfinder inventory."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHFINDER_URL)
            if not soup:
                return articles

            # Look for featured watches or inventory sections
            featured = soup.find("section", class_=re.compile("featured|showcase", re.I))
            if featured:
                watches = featured.find_all("div", class_=re.compile("watch|item|product", re.I))[:5]

                for watch in watches:
                    title_elem = watch.find(["h3", "a"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = watch.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.WATCHFINDER_URL,
                            title=title,
                            summary=summary,
                            source_name="Watchfinder",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Watchfinder error: {e}")

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

    def _scrape_crown_caliber(self) -> list[Article]:
        """Scrape Crown & Caliber inventory."""
        articles = []
        try:
            soup = self.fetch_html(self.CROWN_CALIBER_URL)
            if not soup:
                return articles

            # Look for new arrivals or featured watches
            new_arrivals = soup.find("section", class_=re.compile("new|arrival|featured", re.I))
            if new_arrivals:
                watches = new_arrivals.find_all("div", class_=re.compile("watch|product|item", re.I))[:5]

                for watch in watches:
                    title_elem = watch.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = watch.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.CROWN_CALIBER_URL,
                            title=title,
                            summary=summary,
                            source_name="Crown & Caliber",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Crown & Caliber error: {e}")

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

    def _scrape_watchbox(self) -> list[Article]:
        """Scrape Watchbox inventory."""
        articles = []
        try:
            soup = self.fetch_html(self.WATCHBOX_URL)
            if not soup:
                return articles

            # Look for featured or new watches
            featured = soup.find("section", class_=re.compile("featured|showcase|collection", re.I))
            if featured:
                watches = featured.find_all("div", class_=re.compile("watch|item|card", re.I))[:5]

                for watch in watches:
                    title_elem = watch.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = watch.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.WATCHBOX_URL,
                            title=title,
                            summary=summary,
                            source_name="Watchbox",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Watchbox error: {e}")

        return articles

    def _scrape_bobs_watches(self) -> list[Article]:
        """Scrape Bob's Watches inventory."""
        articles = []
        try:
            soup = self.fetch_html(self.BOBS_WATCHES_URL)
            if not soup:
                return articles

            # Look for what's new or featured
            new_section = soup.find("section", class_=re.compile("new|featured|collection", re.I))
            if new_section:
                watches = new_section.find_all("div", class_=re.compile("watch|product|item", re.I))[:5]

                for watch in watches:
                    title_elem = watch.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = watch.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.BOBS_WATCHES_URL,
                            title=title,
                            summary=summary,
                            source_name="Bob's Watches",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Bob's Watches error: {e}")

        return articles

    def _scrape_hodinkee_shop(self) -> list[Article]:
        """Scrape Hodinkee Shop."""
        articles = []
        try:
            soup = self.fetch_html(self.HODINKEE_SHOP_URL)
            if not soup:
                return articles

            # Look for featured or new arrivals
            featured = soup.find("section", class_=re.compile("featured|new|collection", re.I))
            if featured:
                watches = featured.find_all("div", class_=re.compile("watch|product|item", re.I))[:5]

                for watch in watches:
                    title_elem = watch.find(["h2", "h3"])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                        summary = watch.get_text(strip=True)[:500]

                        articles.append(Article(
                            url=self.HODINKEE_SHOP_URL,
                            title=title,
                            summary=summary,
                            source_name="Hodinkee Shop",
                            source_category=self.category,
                            priority="P2",
                        ))
        except Exception as e:
            log.warning(f"[{self.display_name}] Hodinkee Shop error: {e}")

        return articles
