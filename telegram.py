"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — TELEGRAM SENDING             ║
╚══════════════════════════════════════════════════════════╝

Sends messages as photos with captions (sendPhoto/sendMediaGroup).
Text-only fallback when no image is available.
"""

import json
import time
import requests
from config import TELEGRAM_TOKEN, CHANNEL_ID, ADMIN_CHAT_ID, log


def send_photo(image_url: str, caption: str, chat_id: str = None) -> bool:
    """Send a single photo + caption (HTML, max 1024 chars)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    target = chat_id or CHANNEL_ID

    # Telegram caption limit is 1024 chars
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
        err = result.get("description", "?")
        log.warning(f"Photo rejected: {err}")
        # If photo URL is bad, return False so we can fall back
        return False
    except requests.RequestException as e:
        log.error(f"Photo request error: {e}")
        return False


def send_media_group(image_urls: list, caption: str, chat_id: str = None) -> bool:
    """Send multiple photos as a media group. Caption goes on the first photo."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMediaGroup"
    target = chat_id or CHANNEL_ID

    if not image_urls:
        return False

    # Telegram caption limit is 1024 chars
    if len(caption) > 1024:
        caption = caption[:1020] + "…"

    # Build media array — caption only on first photo
    media = []
    for i, img_url in enumerate(image_urls[:10]):  # Telegram max 10 media
        item = {
            "type": "photo",
            "media": img_url,
        }
        if i == 0:
            item["caption"] = caption
            item["parse_mode"] = "HTML"
        media.append(item)

    try:
        r = requests.post(url, json={
            "chat_id": target,
            "media":   media,
        }, timeout=30)
        result = r.json()
        if result.get("ok"):
            log.info(f"Media group ({len(image_urls)} photos) sent to Telegram")
            return True
        err = result.get("description", "?")
        log.warning(f"Media group rejected: {err}")
        return False
    except requests.RequestException as e:
        log.error(f"Media group request error: {e}")
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


def dispatch(message: str, image_urls: list = None, msg_type: str = ""):
    """Send a message with photo(s). Always tries photo first.

    image_urls: list of image URL strings. Can be empty/None.
    If 1 image: sendPhoto with caption
    If 2+ images: sendMediaGroup with caption on first
    If 0 images: sendMessage with text
    If caption too long for photo: sendPhoto + separate sendMessage
    """
    if not image_urls:
        image_urls = []

    # Filter out None/empty URLs
    image_urls = [u for u in image_urls if u and u.startswith("http")]

    if len(image_urls) >= 2:
        # Multiple images — try media group
        if len(message) <= 1024:
            if not send_media_group(image_urls, message):
                # Fallback: try single photo
                if not send_photo(image_urls[0], message):
                    send_message(message, allow_preview=True)
        else:
            # Caption too long — send photos with short caption, then full text
            short_caption = _extract_title(message)
            if send_media_group(image_urls, short_caption):
                time.sleep(1)
                send_message(message)
            else:
                send_message(message, allow_preview=True)

    elif len(image_urls) == 1:
        # Single image
        if len(message) <= 1024:
            if not send_photo(image_urls[0], message):
                send_message(message, allow_preview=True)
        else:
            # Caption too long — photo with title, then full text
            short_caption = _extract_title(message)
            if send_photo(image_urls[0], short_caption):
                time.sleep(1)
                send_message(message)
            else:
                send_message(message, allow_preview=True)

    else:
        # No images — text only
        send_message(message, allow_preview=True)


def _extract_title(message: str) -> str:
    """Extract first meaningful line as short caption for photo."""
    lines = [l.strip() for l in message.split("\n") if l.strip()]
    if lines:
        # Take first 200 chars of first non-empty line
        return lines[0][:200]
    return ""


def send_admin(text: str) -> bool:
    """Send a message to the admin private chat (for health reports)."""
    if not ADMIN_CHAT_ID:
        log.warning("ADMIN_CHAT_ID not set — skipping admin message")
        return False
    return send_message(text, chat_id=ADMIN_CHAT_ID)
