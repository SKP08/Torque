"""
Wikipedia summaries (title, blurb, photo, coordinates) for the info panels.

Results and photos are cached on disk, so a topic you've looked up once also
works offline. Every failure (no internet, 404, odd response) returns None:
the panels simply don't appear and speech is unaffected.
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from loguru import logger

SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{}"
SEARCH_URL = "https://en.wikipedia.org/w/rest.php/v1/search/title?q={}&limit=1"
USER_AGENT = "TorqueAssistant/0.1 (personal voice assistant; local use)"

TIMEOUT = 4.0
CACHE_DAYS = 30
MAX_IMAGE_BYTES = 3 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def http_get(url: str, timeout: float = TIMEOUT, limit: int = 2_000_000) -> tuple[bytes, str]:
    """(body, content-type). Raises on any network problem."""

    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})

    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(limit + 1)

        if len(body) > limit:
            raise ValueError("response too large")

        return body, response.headers.get("Content-Type", "").split(";")[0].strip().lower()


def first_sentences(text: str, max_chars: int = 240) -> str:
    """Whole sentences up to max_chars (never cut mid-sentence unless one is huge)."""

    text = " ".join((text or "").split())

    if len(text) <= max_chars:
        return text

    out = ""

    for sentence in text.replace("? ", "?|").replace("! ", "!|").replace(". ", ".|").split("|"):

        if out and len(out) + len(sentence) + 1 > max_chars:
            break

        out = f"{out} {sentence}".strip()

    return out if len(out) <= max_chars * 1.4 else out[:max_chars].rsplit(" ", 1)[0] + "..."


class WikiClient:

    def __init__(self, cache_dir: Path, fetch=http_get, clock=time.time):

        self.cache_dir = Path(cache_dir)
        self.images_dir = self.cache_dir / "images"
        self._fetch = fetch
        self._clock = clock

    # ---- cache ---------------------------------------------------

    def _key(self, title: str) -> Path:

        digest = hashlib.sha256(title.strip().lower().encode()).hexdigest()[:24]

        return self.cache_dir / f"{digest}.json"

    def _read_cache(self, title: str, allow_stale: bool):

        path = self._key(title)

        try:
            age_days = (self._clock() - path.stat().st_mtime) / 86400

            if age_days > CACHE_DAYS and not allow_stale:
                return None

            return json.loads(path.read_text(encoding="utf-8"))

        except (OSError, ValueError):
            return None

    def _write_cache(self, title: str, data: dict):

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._key(title).write_text(json.dumps(data), encoding="utf-8")
        except OSError:
            logger.debug("Could not write HUD cache.", exc_info=True)

    # ---- lookups -------------------------------------------------

    def summary(self, title: str):
        """A card dict for `title`, or None."""

        title = (title or "").strip()

        if not title:
            return None

        cached = self._read_cache(title, allow_stale=False)

        if cached is not None:
            return cached or None             # {} marks a remembered miss

        try:
            card = self._lookup(title)

        except Exception:  # noqa: BLE001
            logger.debug(f"Wikipedia lookup failed for {title!r}", exc_info=True)

            stale = self._read_cache(title, allow_stale=True)      # offline: old is better than nothing

            return stale or None

        self._write_cache(title, card or {})

        return card

    def _lookup(self, title: str):

        card = self._summary_request(title)

        if card is None:                                  # no exact page: ask search for the best title
            body, _ = self._fetch(SEARCH_URL.format(urllib.parse.quote(title)))
            pages = json.loads(body).get("pages") or []

            if not pages:
                return None

            card = self._summary_request(pages[0].get("key") or pages[0].get("title", ""))

        return card

    def _summary_request(self, title: str):

        url = SUMMARY_URL.format(urllib.parse.quote(title.replace(" ", "_"), safe=""))

        try:
            body, _ = self._fetch(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

        data = json.loads(body)

        if data.get("type") not in ("standard", None) or not data.get("extract"):
            return None                                   # disambiguation / empty page

        coordinates = data.get("coordinates") or {}
        thumbnail = (data.get("thumbnail") or {}).get("source")

        return {
            "title": data.get("title") or title,
            "description": data.get("description") or "",
            "text": first_sentences(data["extract"]),
            "image_remote": thumbnail,
            "image": self._cache_image(thumbnail),
            "lat": coordinates.get("lat"),
            "lon": coordinates.get("lon"),
            "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page"),
        }

    def _cache_image(self, url):
        """Download a thumbnail once; returns the /cache/... path the UI loads."""

        if not url or not url.startswith("https://upload.wikimedia.org/"):
            return None

        name = hashlib.sha256(url.encode()).hexdigest()[:24]

        for extension in IMAGE_TYPES.values():
            if (self.images_dir / f"{name}{extension}").exists():
                return f"/cache/images/{name}{extension}"

        try:
            body, content_type = self._fetch(url, limit=MAX_IMAGE_BYTES)

            extension = IMAGE_TYPES.get(content_type)

            if not extension or not body:
                return None

            self.images_dir.mkdir(parents=True, exist_ok=True)
            (self.images_dir / f"{name}{extension}").write_bytes(body)

            return f"/cache/images/{name}{extension}"

        except Exception:  # noqa: BLE001
            logger.debug("Could not download a panel image.", exc_info=True)
            return None
