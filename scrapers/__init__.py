"""Watchpoint scrapers — one module per source category."""

from scrapers.base import BaseScraper, RSSMixin
from scrapers.market_analytics import MarketAnalyticsScraper
from scrapers.watch_media import WatchMediaScraper
from scrapers.secondary_market import SecondaryMarketScraper
from scrapers.auctions import AuctionsScraper
from scrapers.industry import IndustryScraper
from scrapers.brands import BrandsScraper
from scrapers.events import EventsScraper
from scrapers.forums import ForumsScraper
from scrapers.macro import MacroIndicatorsScraper

# Registry of all scrapers — instantiated in bot.py
ALL_SCRAPERS = [
    MarketAnalyticsScraper,
    WatchMediaScraper,
    SecondaryMarketScraper,
    AuctionsScraper,
    IndustryScraper,
    BrandsScraper,
    EventsScraper,
    ForumsScraper,
    MacroIndicatorsScraper,
]
