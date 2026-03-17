"""Watchpoint scrapers — one module per source category."""

from scrapers.base import BaseScraper, RSSMixin
from scrapers.market_analytics import MarketAnalyticsScraper
from scrapers.watch_media import WatchMediaScraper
from scrapers.secondary_market import SecondaryMarketScraper
from scrapers.auctions import AuctionScraper
from scrapers.industry import IndustryScraper
from scrapers.brands import BrandScraper
from scrapers.events import EventScraper
from scrapers.forums import ForumScraper
from scrapers.macro import MacroScraper

# Registry of all scrapers — instantiated in bot.py
ALL_SCRAPERS = [
    MarketAnalyticsScraper,
    WatchMediaScraper,
    SecondaryMarketScraper,
    AuctionScraper,
    IndustryScraper,
    BrandScraper,
    EventScraper,
    ForumScraper,
    MacroScraper,
]
