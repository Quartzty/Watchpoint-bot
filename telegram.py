"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM SENDING             ║
╚══════════════════════════════════════════════════════════╝
"""

import time
import requests
from config import TELEGRAM_TOKEN, CHANNEL_ID, ADMIN_CHAT_ID, log


def send_photo(image_url: str, caption: str, chat_id: str = None) -> bool:
    """Send a photo + caption (HTML, max 1024 chars)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    target = chat_id or CHANNEL_ID
    if len(caption) > 1024:
        caption = caption[:1020] + "…"
    try:
        r = requests.post(url, json={
            "chat_id":    target,
            "photo":      image_url,
            "caption":    caption,
            "parse_mode": "HTML",
        }, timeout=30)
        result = r.json()
        if result.get("ok"):
            log.info("Photo sent to Telegram")
            return True
        log.warning(f"Photo rejected: {result.get('description', '?')}")
        return False
    except requests.RequestException as e:
        log.error(f"Photo request error: {e}")
        return False


def send_message(text: str, retry: int = 2, allow_preview: bool = False,
                 chat_id: str = None) -> bool:
    """Send an HTML text message with retry logic."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    target = chat_id or CHANNEL_ID
    payload = {
        "chat_id":                  target,
        "text":                     text,
        "parse_mode":               "HTML",
        "disable_web_page_preview": not allow_preview,
    }

    for attempt in range(1, retry + 2):
        try:
            r = requests.post(url, json=payload, timeout=30)
            result = r.json()

            if result.get("ok"):
                log.info("Message sent to Telegram")
                return True

            err = result.get("description", "Unknown error")
            log.warning(f"Telegram rejected (attempt {attempt}): {err}")

            if "too long" in err.lower():
                return send_split(text, chat_id=target)
            if "can't parse" in err.lower():
                payload["parse_mode"] = ""
                continue
            if "chat not found" in err.lower():
                log.error("TELEGRAM_CHANNEL_ID introuvable — verifie ton .env")
                return False

            time.sleep(5 * attempt)

        except requests.RequestException as e:
            log.error(f"Request error (attempt {attempt}): {e}")
            time.sleep(10)

    log.error("Failed to send after all retries")
    return False


def send_split(text: str, chat_id: str = None) -> bool:
    """Split a message that's too long into multiple parts."""
    max_len = 4000
    parts = []
    while len(text) > max_len:
        cut = text.rfind("\n", 0, max_len)
        cut = cut if cut > 0 else max_len
        parts.append(text[:cut])
        text = text[cut:].strip()
    parts.append(text)

    success = True
    for i, part in enumerate(parts):
        if i > 0:
            time.sleep(1)
        if not send_message(part, retry=1, chat_id=chat_id):
            success = False
    return success


def dispatch(message: str, image_url: str | None, msg_type: str = ""):
    """Send a message with optional photo. Handles all logic for image/text dispatch."""
    is_flash = msg_type in ("NEWS", "FLASH")

    if image_url:
        if len(message) <= 950:
            if not send_photo(image_url, message):
                send_message(message, allow_preview=not is_flash)
        else:
            caption = next((l.strip() for l in message.split("\n") if l.strip()), "")[:200]
            if send_photo(image_url, caption):
                time.sleep(1)
                send_message(message)
            else:
                send_message(message, allow_preview=not is_flash)
    else:
        send_message(message, allow_preview=not is_flash)


def send_admin(text: str) -> bool:
    """Send a message to the admin private chat (for health reports)."""
    if not ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID not set — skipping admin message")
        return False
    return send_message(text, chat_id=ADMIN_CHAT_ID)
