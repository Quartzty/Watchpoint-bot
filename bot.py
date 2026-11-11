#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM BOT v2              ║
║       4 Short + 1 Rich · Direct scraping + Claude        ║
╚══════════════════════════════════════════════════════════╝
"""

import os
import sys
import time
import socket
import schedule
from datetime import datetime

from config import (
    TIMEZONE, TZ_NAME, DAILY_SLOTS, SEND_ON_START, SLOT_GRACE_MINUTES,
    SCRAPE_INTERVAL_MINUTES, SCRAPE_REQUEST_TIMEOUT, validate_config, log,
    DB_PATH, DB_EPHEMERAL, RAILWAY_VOLUME_MOUNT_PATH,
)
from database import (
    init_db, mark_slot_fired, get_fired_slots_today, get_storage_stats,
    record_sent_message, mark_articles_used, record_sent_images, log_health_event,
)
from generators import generate_message, generate_specific, check_models
from telegram import dispatch, send_admin
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

def publish(post) -> bool:
    """Send a post, then record what was actually published: the topic
    (anti-repetition), its articles (never offered to Claude again) and its
    images (never posted again)."""
    delivered, images_sent = dispatch(post.text, post.image_urls, msg_type=post.msg_type)
    if post.summary:
        record_sent_message(post.slot, post.category, post.msg_type, post.summary,
                            success=delivered)
    if delivered or images_sent:   # something visibly went out to the channel
        mark_articles_used(post.article_ids)
    record_sent_images([img for img in post.images if img.url in images_sent],
                       post.category)
    log.info(f"{'Dispatched' if delivered else 'NOT delivered'} [{post.msg_type}] "
             f"{post.category} — {len(post.text)} chars, {len(images_sent)} image(s), "
             f"{len(post.article_ids)} article(s) marked used")
    return delivered


def job(slot: int, slot_type: str):
    """Generate and send a message for a given slot."""
    now = datetime.now(TIMEZONE).strftime("%H:%M %Z")
    log.info("━" * 50)
    log.info(f"Slot {slot} ({slot_type}) triggered at {now}")

    items = generate_message(slot, slot_type)

    if not items:
        log.error(f"No message generated for slot {slot} — skipping send")
        return

    for post in items:
        publish(post)


def check_storage():
    """Say whether the history survives deploys (Railway disk is ephemeral)."""
    stats = get_storage_stats()
    since = (stats["first_message"] or "")[:10] or "—"
    log.info(f"Database: {DB_PATH} — {stats['articles']} articles, {stats['messages']} "
             f"messages (since {since}), {stats['images']} images posted")
    if RAILWAY_VOLUME_MOUNT_PATH:
        log.info(f"   Stored on the Railway volume mounted at {RAILWAY_VOLUME_MOUNT_PATH} (persistent)")
    elif DB_EPHEMERAL:
        msg = ("La base SQLite est sur le disque éphémère de Railway : historique "
               "anti-répétition, articles et images déjà publiés sont effacés à chaque "
               "déploiement. Attachez un volume au service (Railway → service → Volumes, "
               "point de montage /data par exemple) : le bot l'utilisera automatiquement.")
        log.warning(msg)
        log_health_event("storage_ephemeral", "Base SQLite hors volume Railway")
        send_admin(f"⚠️ <b>Watchpoint — stockage</b>\n{msg}")


# ─── SCHEDULER ───────────────────────────────────────────────────────────────

_sent_today: set = set()
_health_report_date = None

HEALTH_REPORT_TIME = "23:55"


def _minutes(hhmm: str) -> int:
    """'HH:MM' -> minutes since midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def check_slots():
    """Check every 30 seconds if a slot should fire (Paris time).

    The loop is single-threaded: a scrape cycle (several minutes) or a restart
    can make it skip a slot's exact minute. A slot therefore fires once a day,
    at its time or late within SLOT_GRACE_MINUTES."""
    global _sent_today
    now_paris = datetime.now(TIMEZONE)
    today = now_paris.strftime("%Y-%m-%d")
    hhmm = now_paris.strftime("%H:%M")
    now_min = now_paris.hour * 60 + now_paris.minute

    # Purge cache if day changed
    _sent_today = {k for k in _sent_today if k.startswith(today)}

    for cfg in DAILY_SLOTS:
        key = f"{today}_slot{cfg['slot']}"
        delay = now_min - _minutes(cfg["time"])
        if key in _sent_today or not 0 <= delay < SLOT_GRACE_MINUTES:
            continue
        _sent_today.add(key)
        mark_slot_fired(cfg["slot"])
        late = f" ({delay} min late)" if delay else ""
        log.info(f"⏰ Slot {cfg['slot']} fired at {hhmm} (Paris){late}")
        job(cfg["slot"], cfg["type"])


def check_health_report():
    """Send the daily health report once a day, from HEALTH_REPORT_TIME."""
    global _health_report_date
    now_paris = datetime.now(TIMEZONE)
    today = now_paris.strftime("%Y-%m-%d")
    if now_paris.strftime("%H:%M") >= HEALTH_REPORT_TIME and _health_report_date != today:
        _health_report_date = today
        daily_health_report()


def setup_schedule():
    """Configure the scheduler."""
    schedule.every(30).seconds.do(check_slots)
    schedule.every(SCRAPE_INTERVAL_MINUTES).minutes.do(run_scrapers)
    schedule.every(1).minutes.do(check_health_report)

    log.info("Scheduler started")
    for cfg in DAILY_SLOTS:
        log.info(f"   → Slot {cfg['slot']} : {cfg['time']} ({cfg['type']}) ({TZ_NAME})")
    log.info(f"   → Late slots still fire within {SLOT_GRACE_MINUTES} minutes")
    log.info(f"   → Scraping every {SCRAPE_INTERVAL_MINUTES} minutes")
    log.info(f"   → Health report at {HEALTH_REPORT_TIME}")


# ─── ENTRYPOINT ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM BOT v2              ║
║       4 Short + 1 Rich · Direct Scraping + Claude        ║
╚══════════════════════════════════════════════════════════╝
""")

    if not validate_config():
        exit(1)

    # feedparser fetches RSS feeds with urllib and no timeout: one feed that
    # never answers would block the whole (single-threaded) bot forever.
    socket.setdefaulttimeout(SCRAPE_REQUEST_TIMEOUT)

    init_db()
    check_storage()

    # Fail loudly (logs + admin chat) if the Claude model is retired/unknown
    check_models()

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
    test_all = os.getenv("TEST_ALL", "false").lower() == "true"
    test_type = os.getenv("TEST_TYPE", "").strip()

    if test_all:
        log.info("╔═══ TEST MODE: ALL TYPES ═══╗")
        all_cats = ["news_flash", "market_signal", "event_flash", "release_flash",
                    "release", "market_update", "analysis", "event"]
        for cat_key in all_cats:
            log.info(f"\n{'━' * 50}")
            log.info(f"Testing: {cat_key}")
            items = generate_specific(cat_key)
            if items:
                for post in items:
                    ok = publish(post)
                    log.info(f"{'✅ Sent' if ok else '❌ Not delivered'} [{post.msg_type}] "
                             f"{post.category} ({len(post.text)} chars, {len(post.image_urls)} img)")
            else:
                log.error(f"❌ No message generated for {cat_key}")
            time.sleep(3)
        log.info("╚═══ TEST COMPLETE ═══╝")
        sys.exit(0)

    if test_type:
        log.info(f"╔═══ TEST MODE: {test_type.upper()} ═══╗")
        items = generate_specific(test_type)
        if items:
            for post in items:
                ok = publish(post)
                log.info(f"{'✅ Sent' if ok else '❌ Not delivered'} [{post.msg_type}] "
                         f"{post.category} ({len(post.text)} chars, {len(post.image_urls)} img)")
        else:
            log.error(f"❌ No message generated for {test_type}")
        log.info("╚═══ TEST COMPLETE ═══╝")
        sys.exit(0)

    # ── NORMAL MODE ───────────────────────────────────────────────────────
    if SEND_ON_START:
        log.info("SEND_ON_START=true → sending slot 0 immediately")
        job(slot=0, slot_type="short")

    log.info("Bot started. Ctrl+C to stop.\n")

    try:
        while True:
            try:
                schedule.run_pending()
            except Exception as e:
                # One failing job must not kill the bot (and the next slots)
                log.exception(f"Scheduled job crashed: {e}")
            time.sleep(15)
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
