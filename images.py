"""
╔══════════════════════════════════════════════════════════╗
║       WATCHPOINT ADVISORY — IMAGE SELECTION              ║
╚══════════════════════════════════════════════════════════╝

Chooses the images of a post and never posts the same picture twice:
- candidates come only from the article(s) the post is about (plus, if none
  of them works, the og:image of those articles' pages);
- each candidate is downloaded and checked: real image, large enough, a
  format and size Telegram accepts when sending a photo by URL;
- duplicates are detected against images already posted, by normalized URL
  (resize/format variants of the same file on CDNs and WordPress) and by a
  perceptual hash (dHash: same picture re-encoded or resized under another
  URL, e.g. one press photo reused by several sites).
"""

import io
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from PIL import Image, UnidentifiedImageError

from articles import page_image_from_html
from config import (
    IMAGE_DEDUP_DAYS, IMAGE_MAX_BYTES, IMAGE_MIN_HEIGHT, IMAGE_MIN_WIDTH,
    USER_AGENT, log,
)
from database import get_recent_sent_images

# Hamming distance (out of 64 bits) at or under which two dHashes are the same
# picture. The same image resized or recompressed differs by ~0-3 bits;
# different photos by 20+. Kept low so that two different watches shot on a
# similar white background are not mistaken for one another.
DUPLICATE_DISTANCE = 5

# Formats Telegram displays as a photo.
_PHOTO_FORMATS = {"JPEG", "PNG", "WEBP"}

# Width/height beyond this ratio: banners, strips — poor post illustrations.
_MAX_ASPECT_RATIO = 3.0

_TIMEOUT = 15

# Query parameters that only change the size / format / quality of one file.
_TRANSFORM_PARAMS = {
    "w", "h", "width", "height", "fit", "crop", "auto", "q", "quality", "fm",
    "format", "dpr", "resize", "size", "s", "ixlib", "ixid", "rect", "ar",
    "scale", "sharp", "blur", "cs", "bg", "trim", "v", "ver", "version",
    "strip", "ssl", "lossless", "zoom", "fp-x", "fp-y", "fp-z", "itok",
}
_EXT = r"(?=\.[a-z0-9]{3,4}$)"
_WP_SIZE_SUFFIX = re.compile(r"-\d{2,5}x\d{2,5}" + _EXT, re.I)   # photo-1024x683.jpg
_SCALED_SUFFIX = re.compile(r"-(?:scaled|e\d{10,})" + _EXT, re.I)  # photo-scaled.jpg
_RETINA_SUFFIX = re.compile(r"@[23]x" + _EXT, re.I)               # photo@2x.jpg


@dataclass
class ImageInfo:
    url: str
    norm_url: str
    dhash: Optional[int] = None
    width: int = 0
    height: int = 0


def normalize_image_url(url: str) -> str:
    """Same file => same string, whatever the resize/format variant."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path
    for pattern in (_WP_SIZE_SUFFIX, _SCALED_SUFFIX, _RETINA_SUFFIX):
        path = pattern.sub("", path)
    query = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRANSFORM_PARAMS
    )
    return urlunsplit(("https", host, path, urlencode(query), ""))


def dhash(img: Image.Image, size: int = 8) -> int:
    """64-bit difference hash: compares the brightness of neighbouring pixels
    on a 9x8 grayscale thumbnail. Robust to resizing and recompression."""
    gray = img.convert("L").resize((size + 1, size), Image.Resampling.LANCZOS)
    px = gray.load()
    value = 0
    for y in range(size):
        for x in range(size):
            value = (value << 1) | (1 if px[x, y] > px[x + 1, y] else 0)
    return value


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _client() -> httpx.Client:
    return httpx.Client(
        timeout=_TIMEOUT,
        follow_redirects=True,
        headers={
            "User-Agent": USER_AGENT,
            # Ask for formats Telegram can display (not AVIF) on negotiating CDNs.
            "Accept": "image/jpeg,image/png,image/webp,image/*;q=0.8,*/*;q=0.5",
        },
    )


def _download(client: httpx.Client, url: str) -> Optional[tuple]:
    """(bytes, content-type), or None if larger than IMAGE_MAX_BYTES."""
    with client.stream("GET", url) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if int(r.headers.get("content-length") or 0) > IMAGE_MAX_BYTES:
            return None
        buf = bytearray()
        for chunk in r.iter_bytes():
            buf.extend(chunk)
            if len(buf) > IMAGE_MAX_BYTES:
                return None
    return bytes(buf), ctype


def inspect_image(url: str, client: httpx.Client) -> Optional[ImageInfo]:
    """Download and check one candidate. None if unusable (reason logged)."""
    short = url[:90]
    try:
        got = _download(client, url)
    except Exception as e:
        log.info(f"Image rejected (download failed): {short} — {e}")
        return None
    if not got:
        log.info(f"Image rejected (over {IMAGE_MAX_BYTES // 1_000_000} MB): {short}")
        return None
    data, ctype = got
    if ctype and not ctype.startswith("image/") and ctype != "application/octet-stream":
        log.info(f"Image rejected (not an image: {ctype}): {short}")
        return None
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            if img.format not in _PHOTO_FORMATS:
                log.info(f"Image rejected (format {img.format}): {short}")
                return None
            if width < IMAGE_MIN_WIDTH or height < IMAGE_MIN_HEIGHT:
                log.info(f"Image rejected (too small {width}x{height}): {short}")
                return None
            if max(width, height) / min(width, height) > _MAX_ASPECT_RATIO:
                log.info(f"Image rejected (banner-shaped {width}x{height}): {short}")
                return None
            fingerprint = dhash(img)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        log.info(f"Image rejected (unreadable): {short} — {e}")
        return None
    return ImageInfo(url=url, norm_url=normalize_image_url(url), dhash=fingerprint,
                     width=width, height=height)


def find_page_image(page_url: str, client: httpx.Client) -> Optional[str]:
    """The page's share image (og:image / twitter:image), if any."""
    try:
        r = client.get(page_url, headers={"Accept": "text/html,application/xhtml+xml"})
        r.raise_for_status()
        if "html" not in r.headers.get("content-type", "html"):
            return None
        return page_image_from_html(r.text, page_url)
    except Exception as e:
        log.info(f"No page image for {page_url[:90]}: {e}")
    return None


def select_images(image_urls: list, page_urls: list = (), max_images: int = 2) -> list:
    """Up to max_images usable images never posted before, in candidate order.

    image_urls: direct image candidates, most relevant first.
    page_urls: article pages whose og:image is tried only if no direct
    candidate is usable."""
    if max_images <= 0 or not (image_urls or page_urls):
        return []

    history = get_recent_sent_images(IMAGE_DEDUP_DAYS)
    posted_urls = {norm for norm, _ in history}
    known_hashes = [h for _, h in history if h is not None]
    chosen, tried = [], set()

    def consider(url: str, client: httpx.Client):
        if not url or not url.startswith("http") or len(chosen) >= max_images:
            return
        norm = normalize_image_url(url)
        if norm in tried:
            return
        tried.add(norm)
        if norm in posted_urls:
            log.info(f"Image skipped (already posted): {url[:90]}")
            return
        info = inspect_image(url, client)
        if not info:
            return
        if any(hamming(info.dhash, h) <= DUPLICATE_DISTANCE for h in known_hashes):
            log.info(f"Image skipped (same picture already posted or in this post): {url[:90]}")
            return
        chosen.append(info)
        known_hashes.append(info.dhash)

    with _client() as client:
        for url in image_urls:
            consider(url, client)
        if not chosen:
            for page in list(page_urls)[:2]:
                og = find_page_image(page, client)
                if og:
                    consider(og, client)
                if chosen:
                    break

    return chosen
