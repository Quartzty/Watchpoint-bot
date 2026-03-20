"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — DATABASE (SQLite)            ║
╚══════════════════════════════════════════════════════════╝

Stores scraped articles, price indices, and historical data.
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Optional
from config import DB_PATH, TIMEZONE, log


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        -- Scraped articles from all sources
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            source_name TEXT NOT NULL,
            source_category TEXT NOT NULL,
            priority TEXT DEFAULT 'P2',
            scraped_at TEXT NOT NULL,
            published_at TEXT,
            used_in_message INTEGER DEFAULT 0,
            raw_html TEXT,
            image_url TEXT
        );

        -- Price index history (WatchCharts, Chrono24, Subdial, etc.)
        CREATE TABLE IF NOT EXISTS price_indices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            index_name TEXT NOT NULL,
            source TEXT NOT NULL,
            value REAL NOT NULL,
            change_pct REAL,
            recorded_at TEXT NOT NULL,
            UNIQUE(index_name, recorded_at)
        );

        -- Individual watch reference prices over time
        CREATE TABLE IF NOT EXISTS watch_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference TEXT NOT NULL,
            brand TEXT NOT NULL,
            model_name TEXT,
            price_eur REAL,
            price_usd REAL,
            price_chf REAL,
            source TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            UNIQUE(reference, source, recorded_at)
        );

        -- Sent messages tracking (replaces sent_topics.json)
        CREATE TABLE IF NOT EXISTS sent_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot INTEGER NOT NULL,
            category TEXT NOT NULL,
            msg_type TEXT NOT NULL,
            topic_summary TEXT,
            sent_at TEXT NOT NULL,
            success INTEGER DEFAULT 1
        );

        -- Slot tracking (replaces sent_slots.json)
        CREATE TABLE IF NOT EXISTS sent_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            slot INTEGER NOT NULL,
            fired_at TEXT NOT NULL,
            UNIQUE(date, slot)
        );

        -- Health events for daily reporting
        CREATE TABLE IF NOT EXISTS health_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        );

        -- Source health tracking (auto-disable broken sources)
        CREATE TABLE IF NOT EXISTS source_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            source_url TEXT NOT NULL,
            consecutive_failures INTEGER DEFAULT 0,
            last_success TEXT,
            last_failure TEXT,
            last_error TEXT,
            disabled INTEGER DEFAULT 0,
            disabled_at TEXT,
            UNIQUE(source_name)
        );

        -- Indexes for performance
        CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(source_category);
        CREATE INDEX IF NOT EXISTS idx_articles_scraped ON articles(scraped_at);
        CREATE INDEX IF NOT EXISTS idx_articles_used ON articles(used_in_message);
        CREATE INDEX IF NOT EXISTS idx_prices_ref ON watch_prices(reference);
        CREATE INDEX IF NOT EXISTS idx_prices_brand ON watch_prices(brand);
        CREATE INDEX IF NOT EXISTS idx_sent_messages_at ON sent_messages(sent_at);
        CREATE INDEX IF NOT EXISTS idx_indices_name ON price_indices(index_name);
    """)
    conn.commit()

    # Migration: add image_url column if not present (for existing databases)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN image_url TEXT")
        conn.commit()
        log.info("Migration: added image_url column to articles")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.close()
    log.info("Database initialized")


# ─── ARTICLES ────────────────────────────────────────────────────────────────

def url_hash(url: str) -> str:
    """Deterministic hash for dedup."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def store_article(url: str, title: str, summary: str, source_name: str,
                  source_category: str, priority: str = "P2",
                  published_at: str = None, raw_html: str = None,
                  image_url: str = None) -> bool:
    """Store an article. Returns False if duplicate (already exists)."""
    conn = get_db()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO articles
            (url_hash, url, title, summary, source_name, source_category, priority, scraped_at, published_at, raw_html, image_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            url_hash(url), url, title, summary, source_name,
            source_category, priority,
            datetime.now(TIMEZONE).isoformat(),
            published_at, raw_html, image_url
        ))
        conn.commit()
        inserted = conn.total_changes > 0
        return inserted
    except Exception as e:
        log.warning(f"Error storing article: {e}")
        return False
    finally:
        conn.close()


def get_fresh_articles(category: str = None, hours: int = 24,
                       unused_only: bool = True, limit: int = 20) -> list:
    """Get recent articles, optionally filtered by category and usage."""
    conn = get_db()
    cutoff = (datetime.now(TIMEZONE) - timedelta(hours=hours)).isoformat()

    query = "SELECT * FROM articles WHERE scraped_at > ?"
    params = [cutoff]

    if category:
        query += " AND source_category = ?"
        params.append(category)

    if unused_only:
        query += " AND used_in_message = 0"

    query += " ORDER BY priority ASC, scraped_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_article_used(article_id: int):
    """Mark an article as used in a message."""
    conn = get_db()
    conn.execute("UPDATE articles SET used_in_message = 1 WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()


# ─── PRICE INDICES ───────────────────────────────────────────────────────────

def store_price_index(index_name: str, source: str, value: float,
                      change_pct: float = None):
    """Store a price index reading."""
    conn = get_db()
    try:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT OR REPLACE INTO price_indices
            (index_name, source, value, change_pct, recorded_at)
            VALUES (?, ?, ?, ?, ?)
        """, (index_name, source, value, change_pct, today))
        conn.commit()
    except Exception as e:
        log.warning(f"Error storing index: {e}")
    finally:
        conn.close()


def get_index_history(index_name: str, days: int = 30) -> list:
    """Get historical values for a price index."""
    conn = get_db()
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM price_indices
        WHERE index_name = ? AND recorded_at > ?
        ORDER BY recorded_at ASC
    """, (index_name, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_indices() -> list:
    """Get the most recent value for each index."""
    conn = get_db()
    rows = conn.execute("""
        SELECT pi.* FROM price_indices pi
        INNER JOIN (
            SELECT index_name, MAX(recorded_at) as max_date
            FROM price_indices GROUP BY index_name
        ) latest ON pi.index_name = latest.index_name AND pi.recorded_at = latest.max_date
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── WATCH PRICES ────────────────────────────────────────────────────────────

def store_watch_price(reference: str, brand: str, model_name: str = None,
                      price_eur: float = None, price_usd: float = None,
                      price_chf: float = None, source: str = ""):
    """Store a watch price observation."""
    conn = get_db()
    try:
        today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
        conn.execute("""
            INSERT OR REPLACE INTO watch_prices
            (reference, brand, model_name, price_eur, price_usd, price_chf, source, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (reference, brand, model_name, price_eur, price_usd, price_chf, source, today))
        conn.commit()
    except Exception as e:
        log.warning(f"Error storing watch price: {e}")
    finally:
        conn.close()


def get_price_trend(reference: str, days: int = 30) -> list:
    """Get price history for a watch reference."""
    conn = get_db()
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM watch_prices
        WHERE reference = ? AND recorded_at > ?
        ORDER BY recorded_at ASC
    """, (reference, cutoff)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SENT MESSAGES ───────────────────────────────────────────────────────────

def record_sent_message(slot: int, category: str, msg_type: str,
                        topic_summary: str, success: bool = True):
    """Record a message that was sent."""
    conn = get_db()
    conn.execute("""
        INSERT INTO sent_messages (slot, category, msg_type, topic_summary, sent_at, success)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (slot, category, msg_type, topic_summary,
          datetime.now(TIMEZONE).isoformat(), int(success)))
    conn.commit()
    conn.close()


def get_recent_topics(days: int = 3) -> list:
    """Get topic summaries from last N days for anti-repetition."""
    conn = get_db()
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT topic_summary FROM sent_messages
        WHERE sent_at > ? AND success = 1 AND topic_summary IS NOT NULL
        ORDER BY sent_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return [r["topic_summary"] for r in rows]


def get_recent_categories(days: int = 3) -> list:
    """Get categories used recently (for weighted rotation)."""
    conn = get_db()
    cutoff = (datetime.now(TIMEZONE) - timedelta(days=days)).isoformat()
    rows = conn.execute("""
        SELECT category, sent_at FROM sent_messages
        WHERE sent_at > ? AND success = 1
        ORDER BY sent_at DESC
    """, (cutoff,)).fetchall()
    conn.close()
    return [{"category": r["category"], "sent_at": r["sent_at"]} for r in rows]


# ─── SLOT TRACKING ───────────────────────────────────────────────────────────

def mark_slot_fired(slot: int):
    """Mark a slot as fired today."""
    conn = get_db()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    try:
        conn.execute("""
            INSERT OR IGNORE INTO sent_slots (date, slot, fired_at)
            VALUES (?, ?, ?)
        """, (today, slot, datetime.now(TIMEZONE).isoformat()))
        conn.commit()
    except Exception as e:
        log.warning(f"Error marking slot: {e}")
    finally:
        conn.close()


def get_fired_slots_today() -> set:
    """Get slots already fired today."""
    conn = get_db()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT slot FROM sent_slots WHERE date = ?", (today,)
    ).fetchall()
    conn.close()
    return {r["slot"] for r in rows}


# ─── HEALTH EVENTS ──────────────────────────────────────────────────────────

def log_health_event(event_type: str, message: str):
    """Log a health event for daily reporting."""
    conn = get_db()
    conn.execute("""
        INSERT INTO health_events (event_type, message, created_at)
        VALUES (?, ?, ?)
    """, (event_type, message, datetime.now(TIMEZONE).isoformat()))
    conn.commit()
    conn.close()


def get_health_events_today() -> list:
    """Get all health events from today."""
    conn = get_db()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT * FROM health_events
        WHERE created_at LIKE ?
        ORDER BY created_at ASC
    """, (f"{today}%",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SOURCE HEALTH TRACKING ─────────────────────────────────────────────────

MAX_CONSECUTIVE_FAILURES = 3
AUTO_REENABLE_HOURS = 6


def record_source_success(source_name: str, source_url: str):
    """Record a successful fetch for a source. Resets failure count."""
    conn = get_db()
    now = datetime.now(TIMEZONE).isoformat()
    conn.execute("""
        INSERT INTO source_health (source_name, source_url, consecutive_failures, last_success, disabled)
        VALUES (?, ?, 0, ?, 0)
        ON CONFLICT(source_name) DO UPDATE SET
            consecutive_failures = 0,
            last_success = ?,
            source_url = ?
    """, (source_name, source_url, now, now, source_url))
    conn.commit()
    conn.close()


def record_source_failure(source_name: str, source_url: str, error: str) -> bool:
    """Record a failed fetch. Returns True if source was just disabled."""
    conn = get_db()
    now = datetime.now(TIMEZONE).isoformat()

    # Upsert: increment failure count
    conn.execute("""
        INSERT INTO source_health (source_name, source_url, consecutive_failures, last_failure, last_error)
        VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(source_name) DO UPDATE SET
            consecutive_failures = consecutive_failures + 1,
            last_failure = ?,
            last_error = ?,
            source_url = ?
    """, (source_name, source_url, now, error, now, error, source_url))
    conn.commit()

    # Check if we should disable
    row = conn.execute(
        "SELECT consecutive_failures, disabled FROM source_health WHERE source_name = ?",
        (source_name,)
    ).fetchone()
    conn.close()

    if row and row["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES and not row["disabled"]:
        _disable_source(source_name)
        log_health_event("source_disabled", f"{source_name} désactivée après {MAX_CONSECUTIVE_FAILURES} échecs consécutifs ({error})")
        return True

    return False


def _disable_source(source_name: str):
    """Disable a source after too many failures."""
    conn = get_db()
    now = datetime.now(TIMEZONE).isoformat()
    conn.execute("""
        UPDATE source_health SET disabled = 1, disabled_at = ? WHERE source_name = ?
    """, (now, source_name))
    conn.commit()
    conn.close()


def is_source_disabled(source_name: str) -> bool:
    """Check if a source is currently disabled. Auto-re-enables after AUTO_REENABLE_HOURS."""
    conn = get_db()
    row = conn.execute(
        "SELECT disabled, disabled_at FROM source_health WHERE source_name = ?",
        (source_name,)
    ).fetchone()
    conn.close()

    if not row or not row["disabled"]:
        return False

    # Auto re-enable after timeout
    if row["disabled_at"]:
        disabled_at = datetime.fromisoformat(row["disabled_at"])
        now = datetime.now(TIMEZONE)
        if (now - disabled_at) > timedelta(hours=AUTO_REENABLE_HOURS):
            # Re-enable
            conn = get_db()
            conn.execute("""
                UPDATE source_health SET disabled = 0, consecutive_failures = 0 WHERE source_name = ?
            """, (source_name,))
            conn.commit()
            conn.close()
            log.info(f"Source {source_name} auto-ré-activée après {AUTO_REENABLE_HOURS}h")
            log_health_event("source_reenabled", f"{source_name} auto-ré-activée après {AUTO_REENABLE_HOURS}h")
            return False

    return True


def get_broken_sources() -> list:
    """Get all sources that are currently disabled or have recent failures."""
    conn = get_db()
    rows = conn.execute("""
        SELECT source_name, source_url, consecutive_failures, last_success, last_failure,
               last_error, disabled, disabled_at
        FROM source_health
        WHERE disabled = 1 OR consecutive_failures >= ?
        ORDER BY disabled DESC, consecutive_failures DESC
    """, (MAX_CONSECUTIVE_FAILURES,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
