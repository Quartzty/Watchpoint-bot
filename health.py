"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — HEALTH MONITORING            ║
╚══════════════════════════════════════════════════════════╝

Sends a daily health report to the admin private chat.
"""

from datetime import datetime
from config import TIMEZONE, ADMIN_CHAT_ID, log
from database import get_health_events_today, get_fired_slots_today, get_db
from telegram import send_admin


def daily_health_report():
    """Generate and send the daily health report to admin."""
    if not ADMIN_CHAT_ID:
        log.info("No ADMIN_CHAT_ID set — skipping health report")
        return

    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")

    # ── Slots fired today ────────────────────────────────────────────────
    fired = get_fired_slots_today()
    slots_status = []
    slot_names = {0: "08:30 Flash", 1: "11:00 Rich", 2: "14:00 Flash", 3: "18:00 Rich", 4: "21:00 Flash"}
    for slot_num, name in slot_names.items():
        status = "sent" if slot_num in fired else "missed"
        slots_status.append(f"  {'✅' if status == 'sent' else '❌'} {name}")

    # ── Messages sent today ──────────────────────────────────────────────
    conn = get_db()
    msgs = conn.execute("""
        SELECT category, msg_type, topic_summary, success
        FROM sent_messages WHERE sent_at LIKE ?
    """, (f"{today}%",)).fetchall()
    conn.close()

    sent_ok = sum(1 for m in msgs if m["success"])
    sent_fail = sum(1 for m in msgs if not m["success"])

    categories_used = [m["category"] for m in msgs if m["success"]]
    cat_summary = ", ".join(categories_used) if categories_used else "aucune"

    # ── Scraping stats ───────────────────────────────────────────────────
    conn = get_db()
    articles_today = conn.execute("""
        SELECT COUNT(*) as cnt FROM articles WHERE scraped_at LIKE ?
    """, (f"{today}%",)).fetchone()["cnt"]

    new_articles = conn.execute("""
        SELECT source_category, COUNT(*) as cnt FROM articles
        WHERE scraped_at LIKE ? GROUP BY source_category ORDER BY cnt DESC
    """, (f"{today}%",)).fetchall()
    conn.close()

    scrape_lines = []
    for row in new_articles:
        scrape_lines.append(f"  {row['source_category']}: {row['cnt']} articles")

    # ── Health events (errors, blocks) ───────────────────────────────────
    events = get_health_events_today()
    error_lines = []
    for ev in events:
        error_lines.append(f"  ⚠️ [{ev['event_type']}] {ev['message'][:100]}")

    # ── Build report ─────────────────────────────────────────────────────
    nl = "\n"
    slots_block = nl.join(slots_status)
    scrape_block = nl.join(scrape_lines) if scrape_lines else "  (aucun scraping aujourd'hui)"
    errors_block = nl.join(error_lines)

    report = f"""<b>📊 WATCHPOINT — Rapport quotidien</b>
<b>{now.strftime('%A %d %B %Y')}</b>

<b>Messages</b>
  Envoyés : <b>{sent_ok}</b> | Échoués : <b>{sent_fail}</b>
  Catégories : {cat_summary}

<b>Slots</b>
{slots_block}

<b>Scraping</b>
  Articles collectés : <b>{articles_today}</b>
{scrape_block}"""

    if error_lines:
        report += f"""

<b>Alertes</b>
{errors_block}"""

    if not error_lines and sent_fail == 0:
        report += "\n\n✅ Aucune erreur aujourd'hui."

    # ── Send ─────────────────────────────────────────────────────────────
    success = send_admin(report)
    if success:
        log.info("Daily health report sent to admin")
    else:
        log.error("Failed to send daily health report")
