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

# claude-sonnet-4-20250514 a été retiré par Anthropic le 15/06/2026 : l'API
# répond 404 à chaque appel et plus aucun message n'était généré.
# Claude Sonnet 5.5 est le Sonnet actuel. Surchargeable sans redéploiement de
# code via les variables MODEL_FLASH / MODEL_RICH (ex. sur Railway).
MODEL_FLASH = (os.getenv("MODEL_FLASH") or "claude-sonnet-5-5")   # Short messages
MODEL_RICH  = (os.getenv("MODEL_RICH") or "claude-sonnet-5-5")    # Detailed content

# Effort (profondeur de réflexion) : "low" | "medium" | "high" | "xhigh" | "max".
# "low" suffit pour des messages courts ; "medium" pour le message riche du jour.
EFFORT_FLASH = (os.getenv("EFFORT_FLASH") or "low")
EFFORT_RICH  = (os.getenv("EFFORT_RICH") or "medium")

# Plafond de tokens en sortie (réflexion + message). Ce n'est pas une cible :
# la longueur réelle est imposée par le prompt et truncate_message().
# L'ancien plafond (300 / 800) laisserait la réflexion tronquer le message.
MAX_TOKENS = 16000

# ─── SCHEDULE ────────────────────────────────────────────────────────────────
# 5 messages/jour — 4 Short + 1 Rich (18h00)
# Horaires en heure Paris

DAILY_SLOTS = [
    {"time": "08:30", "slot": 0, "type": "short"},    # Short — matin
    {"time": "11:00", "slot": 1, "type": "short"},     # Short — milieu de matinée
    {"time": "14:00", "slot": 2, "type": "short"},     # Short — début d'après-midi
    {"time": "18:00", "slot": 3, "type": "rich"},      # Rich — le message consistant du jour
    {"time": "21:00", "slot": 4, "type": "short"},     # Short — soirée
]

# ─── CONTENT CATEGORIES ─────────────────────────────────────────────────────

# Short slots: concise messages with image, 40-100 words
SHORT_CATEGORIES = [
    "news_flash",       # Breaking news, appointments, partnerships
    "market_signal",    # Quick price move or index change
    "event_flash",      # Upcoming auction or event date
    "release_flash",    # Quick release announcement (not detailed)
]

# Rich slots: detailed content with analysis (1 per day at 18h)
RICH_CATEGORIES = [
    "release",          # New watch launches — detailed
    "market_update",    # Full secondary market data
    "analysis",         # Industry reports and studies
    "event",            # Major auction results, fair coverage
    "discontinuation",  # End of production signals
]

# Keep backward compat
FLASH_CATEGORIES = SHORT_CATEGORIES

# Weighted rotation: categories with higher weights appear more often
RICH_WEIGHTS = {
    "market_update":    3,    # Most frequent — always relevant data
    "release":          2,    # New launches drive engagement
    "analysis":         2,    # Industry reports are high-value
    "event":            1,    # Only for big sales
    "discontinuation":  1,    # Rare but impactful
}

# ─── SCRAPING ────────────────────────────────────────────────────────────────

# Un créneau en retard (ex. bloqué par un cycle de scraping) part quand même
# s'il reste dans cette fenêtre après son heure prévue.
SLOT_GRACE_MINUTES = 20

SCRAPE_INTERVAL_MINUTES = 60        # How often to run the scrape cycle
SCRAPE_REQUEST_TIMEOUT  = 30        # HTTP timeout per source (seconds)
SCRAPE_DELAY_BETWEEN    = 2         # Seconds between requests (rate limiting)
USER_AGENT = "WatchpointBot/1.0 (watch market intelligence; contact@watchpoint.fr)"

# ─── DATABASE ────────────────────────────────────────────────────────────────

# Sur Railway, le disque du conteneur est éphémère : sans volume, la base est
# effacée à chaque (re)déploiement — historique anti-répétition, articles et
# images déjà utilisés compris. Quand un volume est attaché, Railway expose son
# point de montage dans RAILWAY_VOLUME_MOUNT_PATH : la base y est alors placée
# automatiquement (même si DB_PATH pointe hors du volume).
RAILWAY_VOLUME_MOUNT_PATH = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
ON_RAILWAY = any(os.getenv(k) for k in (
    "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID", "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_DEPLOYMENT_ID", "RAILWAY_ENVIRONMENT",
))


def _resolve_db_path() -> str:
    configured = os.getenv("DB_PATH") or "watchpoint.db"
    path = os.path.abspath(configured)
    if RAILWAY_VOLUME_MOUNT_PATH:
        volume = os.path.abspath(RAILWAY_VOLUME_MOUNT_PATH)
        if os.path.commonpath([path, volume]) != volume:
            path = os.path.join(volume, os.path.basename(configured))
    return path


DB_PATH = _resolve_db_path()
DB_ON_VOLUME = bool(RAILWAY_VOLUME_MOUNT_PATH)
DB_EPHEMERAL = ON_RAILWAY and not DB_ON_VOLUME

# ─── ARTICLES & IMAGES ───────────────────────────────────────────────────────

# Un article RSS publié il y a plus longtemps n'est plus proposé à Claude
# (sinon, après chaque remise à zéro de la base, d'anciens articles repassent
# pour « frais »).
ARTICLE_MAX_AGE_HOURS = 72

# Images : une image (même URL normalisée ou même empreinte visuelle) déjà
# publiée dans cette fenêtre n'est pas réutilisée.
IMAGE_DEDUP_DAYS = 90
MAX_IMAGES_PER_POST = 2
IMAGE_MIN_WIDTH = 400           # en dessous : vignette / icône / logo
IMAGE_MIN_HEIGHT = 250
IMAGE_MAX_BYTES = 5 * 1024 * 1024   # limite Telegram pour une photo envoyée par URL

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
    log.info(f"   Flash model: {MODEL_FLASH} (effort {EFFORT_FLASH})")
    log.info(f"   Rich model : {MODEL_RICH} (effort {EFFORT_RICH})")
    return True
