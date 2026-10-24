import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

_UNITS = {
    "s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
}

_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
}

_NUMBER = r"\d+(?:\.\d+)?|" + "|".join(sorted((re.escape(w) for w in _WORDS), key=len, reverse=True))
_UNIT = "|".join(sorted(_UNITS, key=len, reverse=True))
_PART = re.compile(rf"(?P<n>{_NUMBER})\s*(?P<u>{_UNIT})\b")
_HALF = re.compile(r"\bhalf (?:an |a )?(?P<u>hour|minute)\b")
_AND_HALF = re.compile(rf"(?P<n>{_NUMBER}) and a half (?P<u>hours?|minutes?)\b")
_UNIT_AND_HALF = re.compile(rf"(?P<n>{_NUMBER})\s*(?P<u>hours?|minutes?) and a half\b")

MAX_SECONDS = 24 * 3600


def parse_duration(text: str):
    """'5 minutes', 'an hour and a half', '1 hour 30 minutes', 'half an hour' -> seconds (or None)."""

    text = (text or "").lower().replace("-", " ")

    total = 0.0
    found = False

    for m in _AND_HALF.finditer(text):
        unit = _UNITS[m.group("u").rstrip("s")] if m.group("u").rstrip("s") in _UNITS else 60
        total += (_value(m.group("n")) + 0.5) * unit
        found = True

    text = _AND_HALF.sub(" ", text)

    for m in _UNIT_AND_HALF.finditer(text):
        total += (_value(m.group("n")) + 0.5) * _UNITS[m.group("u").rstrip("s")]
        found = True

    text = _UNIT_AND_HALF.sub(" ", text)

    for m in _HALF.finditer(text):
        total += 0.5 * _UNITS[m.group("u")]
        found = True

    text = _HALF.sub(" ", text)

    for m in _PART.finditer(text):
        total += _value(m.group("n")) * _UNITS[m.group("u")]
        found = True

    if not found or total <= 0:
        return None

    return int(round(min(total, MAX_SECONDS)))


def _value(token: str) -> float:
    return float(token) if token[0].isdigit() else float(_WORDS[token])


def spoken_duration(seconds: float) -> str:
    seconds = int(round(seconds))

    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"

    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)

    parts = []

    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs and not hours:
        parts.append(f"{secs} second{'s' if secs != 1 else ''}")

    return " and ".join(parts)


class TimerStore:
    """Timers and reminders, saved to a small JSON file so they survive a restart."""

    def __init__(self, path, clock=time.time):
        self.path = Path(path) if path else None
        self.clock = clock
        self._lock = threading.Lock()
        self._items = self._load()

    # ---- persistence ----

    def _load(self):
        if not self.path or not self.path.exists():
            return []

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return [i for i in data if isinstance(i, dict) and "due" in i and "id" in i]
        except (OSError, ValueError):
            return []

    def _save(self):
        if not self.path:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)

        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items), encoding="utf-8")
        os.replace(tmp, self.path)

    # ---- API ----

    def add(self, seconds: float, label: str = "", kind: str = "timer") -> dict:
        item = {
            "id": uuid.uuid4().hex[:8],
            "kind": kind,
            "label": label.strip(),
            "seconds": int(seconds),
            "due": self.clock() + seconds,
        }

        with self._lock:
            self._items.append(item)
            self._save()

        return dict(item)

    def active(self) -> list:
        with self._lock:
            return sorted((dict(i) for i in self._items), key=lambda i: i["due"])

    def remaining(self, item) -> float:
        return max(0.0, item["due"] - self.clock())

    def cancel(self, kind=None) -> int:
        with self._lock:
            keep = [i for i in self._items if kind and i["kind"] != kind]
            removed = len(self._items) - len(keep)
            self._items = keep
            self._save()

        return removed

    def pop_due(self) -> list:
        """Remove and return everything that has come due (oldest first)."""

        with self._lock:
            now = self.clock()
            due = sorted((i for i in self._items if i["due"] <= now), key=lambda i: i["due"])

            if due:
                gone = {i["id"] for i in due}
                self._items = [i for i in self._items if i["id"] not in gone]
                self._save()

        return due


_default = None


def default_store() -> "TimerStore":
    """The one shared store (the brain's skills and the alert watcher both use it)."""

    global _default

    if _default is None:
        from torque.paths import TIMERS_FILE

        _default = TimerStore(TIMERS_FILE)

    return _default
