"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — CONFIGURATION                ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import logging
from dotenv import load_dotenv
import pytz

load_dotenv()

# ─── LOGGING ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("watchpoint_bot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("watchpoint")

# ─── SECRETS ─────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID        = os.getenv("TELEGRAM_CHANNEL_ID", "")
ADMIN_CHAT_ID     = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")  # Private admin chat for health reports
ANTHROPIC_KEY     = os.getenv("ANTHROPIC_API_KEY", "")
SEND_ON_START     = os.getenv("SEND_ON_START", "false").lower() == "true"

# ─── TIMEZONE ────────────────────────────────────────────────────────────────

TZ_NAME  = os.getenv("TIMEZONE", "Europe/Paris")
TIMEZONE = pytz.timezone(TZ_NAME)

# ─── MODELS ──────────────────────────────────────────────────────────────────

MODEL_FLASH = "claude-sonnet-4-20250514"    # Sonnet for all messages — better quality + humanized tone
MODEL_RICH  = "claude-sonnet-4-20250514"    # Sonnet for detailed content

# ─── SCHEDULE ────────────────────────────────────────────────────────────────
# 5 messages/jour — 3 Flash (courts) + 2 Rich (détaillés)
# Horaires en heure Paris

DAILY_SLOTS = [
    {"time": "08:30", "slot": 0, "type": "flash"},   # Flash — matin
    {"time": "11:00", "slot": 1, "type": "rich"},     # Rich — milieu de matinée
    {"time": "14:00", "slot": 2, "type": "flash"},    # Flash — début d'après-midi
    {"time": "18:00", "slot": 3, "type": "rich"},     # Rich — fin d'après-midi
    {"time": "21:00", "slot": 4, "type": "flash"},    # Flash — soirée
]

# ─── CONTENT CATEGORIES ─────────────────────────────────────────────────────

# Flash slots: short, punchy, one-fact messages. NO releases.
FLASH_CATEGORIES = [
    "news_flash",       # Breaking news, appointments, partnerships
    "market_signal",    # Quick price move or index change
    "event_flash",      # Upcoming auction or event date
]

# Rich slots: detailed content with analysis
RICH_CATEGORIES = [
    "release",          # New watch launches
    "discontinuation",  # End of production signals
    "market_update",    # Full secondary market data
    "analysis",         # Industry reports and studies
    "event",            # Major auction results, fair coverage
]

# Weighted rotation: categories with higher weights appear more often
RICH_WEIGHTS = {
    "market_update":    3,    # Most frequent — always relevant data
    "release":          2,    # New launches drive engagement
    "analysis":         2,    # Industry reports are high-value
    "event":            1,    # Only for big sales
    "discontinuation":  1,    # Rare but impactful
}

# ─── SCRAPING ────────────────────────────────────────────────────────────────

SCRAPE_INTERVAL_MINUTES = 60        # How often to run the scrape cycle
SCRAPE_REQUEST_TIMEOUT  = 30        # HTTP timeout per source (seconds)
SCRAPE_DELAY_BETWEEN    = 2         # Seconds between requests (rate limiting)
USER_AGENT = "WatchpointBot/1.0 (watch market intelligence; contact@watchpoint.fr)"

# ─── DATABASE ────────────────────────────────────────────────────────────────

DB_PATH = os.getenv("DB_PATH", "watchpoint.db")

# ─── VALIDATION ──────────────────────────────────────────────────────────────

def validate_config() -> bool:
    """Check all required env vars are set."""
    missing = [k for k, v in {
        "TELEGRAM_BOT_TOKEN":  TELEGRAM_TOKEN,
        "TELEGRAM_CHANNEL_ID": CHANNEL_ID,
        "ANTHROPIC_API_KEY":   ANTHROPIC_KEY,
    }.items() if not v]

    if missing:
        log.error(f"Missing environment variables: {', '.join(missing)}")
        return False

    from datetime import datetime
    log.info("Config OK")
    log.info(f"   Channel ID : {CHANNEL_ID}")
    log.info(f"   Admin chat : {ADMIN_CHAT_ID or 'not set'}")
    log.info(f"   Timezone   : {TZ_NAME}")
    log.info(f"   Heure Paris: {datetime.now(TIMEZONE).strftime('%H:%M')}")
    log.info(f"   Flash model: {MODEL_FLASH}")
    log.info(f"   Rich model : {MODEL_RICH}")
    return True
