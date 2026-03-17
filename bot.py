#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM BOT v2              ║
║       5 messages/jour · 3 Flash + 2 Rich                 ║
║       Direct scraping + Claude formatting                 ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import schedule
from datetime import datetime

from config import (
    TIMEZONE, TZ_NAME, DAILY_SLOTS, SEND_ON_START,
    SCRAPE_INTERVAL_MINUTES, validate_config, log,
)
from database import init_db, mark_slot_fired, get_fired_slots_today
from generators import generate_message, generate_specific
from telegram import dispatch
from health import daily_health_report
from scrapers import ALL_SCRAPERS


# ─── SCRAPE CYCLE ────────────────────────────────────────────────────────────

def run_scrapers():
    """Run all scrapers. Called every SCRAPE_INTERVAL_MINUTES."""
    log.info("━" * 40)
    log.info("Starting scrape cycle")

    total_stats = {"fetched": 0, "new": 0, "errors": 0}

    for ScraperClass in ALL_SCRAPERS:
        try:
            scraper = ScraperClass()
            stats = scraper.run()
            scraper.close()

            total_stats["fetched"] += stats.get("fetched", 0)
            total_stats["new"] += stats.get("new", 0)
            total_stats["errors"] += stats.get("errors", 0)

            if stats.get("new", 0) > 0:
                log.info(f"  [{scraper.display_name}] {stats['new']} new / {stats['fetched']} fetched")
        except Exception as e:
            log.error(f"  [{ScraperClass.__name__}] Failed: {e}")
            total_stats["errors"] += 1

    log.info(f"Scrape complete: {total_stats['new']} new articles, "
             f"{total_stats['fetched']} total, {total_stats['errors']} errors")


# ─── MESSAGE JOB ─────────────────────────────────────────────────────────────

def job(slot: int, slot_type: str):
    """Generate and send a message for a given slot."""
    now = datetime.now(TIMEZONE).strftime("%H:%M %Z")
    log.info("━" * 50)
    log.info(f"Slot {slot} ({slot_type}) triggered at {now}")

    items = generate_message(slot, slot_type)

    if not items:
        log.error(f"No message generated for slot {slot} — skipping send")
        return

    for text, image_url, msg_type, cat_key in items:
        dispatch(text, image_url, msg_type=msg_type)
        log.info(f"Dispatched [{msg_type}] {cat_key}")


# ─── SCHEDULER ───────────────────────────────────────────────────────────────

_sent_today: set = set()


def check_slots():
    """Check every 30 seconds if a slot should fire (Paris time)."""
    global _sent_today
    now_paris = datetime.now(TIMEZONE)
    today = now_paris.strftime("%Y-%m-%d")
    hhmm = now_paris.strftime("%H:%M")

    # Purge cache if day changed
    _sent_today = {k for k in _sent_today if k.startswith(today)}

    for cfg in DAILY_SLOTS:
        key = f"{today}_slot{cfg['slot']}"
        if hhmm == cfg["time"] and key not in _sent_today:
            _sent_today.add(key)
            mark_slot_fired(cfg["slot"])
            log.info(f"⏰ Slot {cfg['slot']} fired at {hhmm} (Paris)")
            job(cfg["slot"], cfg["type"])


def check_health_report():
    """Send daily health report at 23:59."""
    now_paris = datetime.now(TIMEZONE)
    if now_paris.strftime("%H:%M") == "23:59":
        daily_health_report()


def setup_schedule():
    """Configure the scheduler."""
    # Slot checks every 30 seconds
    schedule.every(30).seconds.do(check_slots)

    # Scrape cycle
    schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(run_scrapers)

    # Health report check every minute
    schedule.every(1).minutes.do(check_health_report)

    log.info("Scheduler started")
    for cfg in DAILY_SLOTS:
        log.info(f"   → Slot {cfg['slot']} : {cfg['time']} ({cfg['type']}) ({TZ_NAME})")
    log.info(f"   → Scraping every {SCRAPE_INTERVAL_MINUTES} minutes")
    log.info(f"   → Health report at 23:59")


# ─── ENTRYPOINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM BOT v2              ║
║       3 Flash + 2 Rich · Direct Scraping + Claude        ║
╚══════════════════════════════════════════════════════════╝
""")

    if not validate_config():
        exit(1)

    # Initialize database
    init_db()

    # Load already-fired slots from DB
    fired = get_fired_slots_today()
    today = datetime.now(TIMEZONE).strftime("%Y-%m-%d")
    _sent_today.update(f"{today}_slot{s}" for s in fired)
    if _sent_today:
        log.info(f"{len(_sent_today)} slot(s) already fired today: {fired}")

    # Initial scrape on startup
    log.info("Running initial scrape cycle...")
    run_scrapers()

    # Setup scheduler
    setup_schedule()

    # ── TEST MODE ─────────────────────────────────────────────────────────
    # TEST_ALL=true      → sends one message of each type then exits
    # TEST_TYPE=category → sends one message of that specific category then exits
    # Categories: news_flash, market_signal, event_flash, release, market_update, analysis, event, discontinuation
    test_all = os.getenv("TEST_ALL", "false").lower() == "true"
    test_type = os.getenv("TEST_TYPE", "").strip()

    if test_all:
        log.info("╔═══ TEST MODE: ALL TYPES ═══╗")
        all_cats = ["news_flash", "market_signal", "event_flash",
                    "release", "market_update", "analysis", "event"]
        for cat_key in all_cats:
            log.info(f"\n{'━' * 50}")
            log.info(f"Testing: {cat_key}")
            items = generate_specific(cat_key)
            if items:
                for text, image_url, msg_type, ckey in items:
                    dispatch(text, image_url, msg_type=msg_type)
                    log.info(f"✅ Sent [{msg_type}] {ckey} ({len(text)} chars)")
            else:
                log.error(f"❌ No message generated for {cat_key}")
            time.sleep(3)  # Avoid Telegram rate limits
        log.info("╚═══ TEST COMPLETE ═══╝")
        sys.exit(0)

    if test_type:
        log.info(f"╔═══ TEST MODE: {test_type.upper()} ═══╗")
        items = generate_specific(test_type)
        if items:
            for text, image_url, msg_type, ckey in items:
                dispatch(text, image_url, msg_type=msg_type)
                log.info(f"✅ Sent [{msg_type}] {ckey} ({len(text)} chars)")
        else:
            log.error(f"❌ No message generated for {test_type}")
        log.info("╚═══ TEST COMPLETE ═══╝")
        sys.exit(0)

    # ── NORMAL MODE ───────────────────────────────────────────────────────
    if SEND_ON_START:
        log.info("SEND_ON_START=true → sending slot 0 immediately")
        job(slot=0, slot_type="flash")

    log.info("Bot started. Ctrl+C to stop.\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(15)
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
