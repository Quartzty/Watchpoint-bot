"""Watchpoint scrapers — one module per source category."""

from scrapers.base import BaseScraper, RSSMixin
from scrapers.market_analytics import MarketAnalyticsScraper
from scrapers.watch_media import WatchMediaScraper
from scrapers.secondary_market import SecondaryMarketScraper
from scrapers.auctions import AuctionsScraper
from scrapers.industry import IndustryScraper
from scrapers.events import EventsScraper
from scrapers.forums import ForumsScraper
from scrapers.macro import MacroIndicatorsScraper

# Registry of all scrapers — instantiated in bot.py
ALL_SCRAPERS = [
    WatchMediaScraper,         # RSS feeds — most reliable
    MarketAnalyticsScraper,    # Price indices & analytics
    SecondaryMarketScraper,    # Bezel, Wristcheck, Kalshi
    AuctionsScraper,           # Phillips, Sotheby's, Christie's, Antiquorum, Bonhams
    IndustryScraper,           # FH Swiss, Swatch Group, WoS
    EventsScraper,             # W&W, Geneva Watch Days, GPHG
    ForumsScraper,             # Reddit, WatchUSeek, Rolex Forums
    MacroIndicatorsScraper,    # Trading Economics
]
