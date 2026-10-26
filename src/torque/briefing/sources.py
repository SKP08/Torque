"""Where the morning briefing gets its facts. Every source fails soft (returns None / []):
a briefing without the weather is still a briefing."""

import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone

from loguru import logger

WEATHER_CODES = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rainy", 65: "heavy rain",
    71: "light snow", 73: "snowy", 75: "heavy snow", 80: "showery", 81: "showery", 82: "stormy showers",
    95: "thunderstorms", 96: "thunderstorms", 99: "thunderstorms",
}


def _get_json(url, timeout=6):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Torque"}), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def fetch_weather(city="", lat=None, lon=None, getter=_get_json):
    """Open-Meteo (free, no key). -> {'temp': 24, 'high': 29, 'low': 20, 'sky': 'clear', 'rain': 10, 'place': 'Delhi'} or None."""

    try:
        place = city

        if lat is None or lon is None:
            if not city:
                return None

            found = getter("https://geocoding-api.open-meteo.com/v1/search?count=1&name=" + urllib.parse.quote(city))
            top = (found.get("results") or [None])[0]

            if not top:
                return None

            lat, lon, place = top["latitude"], top["longitude"], top.get("name", city)

        data = getter(
            f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
            "&timezone=auto&forecast_days=1")

        return {
            "temp": round(data["current"]["temperature_2m"]),
            "sky": WEATHER_CODES.get(int(data["current"]["weather_code"]), ""),
            "high": round(data["daily"]["temperature_2m_max"][0]),
            "low": round(data["daily"]["temperature_2m_min"][0]),
            "rain": int(data["daily"]["precipitation_probability_max"][0] or 0),
            "place": place,
        }

    except Exception:  # noqa: BLE001
        logger.debug("Weather unavailable.", exc_info=True)
        return None


# ---------------------------------------------------------------- calendar (.ics)

def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def _parse_dt(value, params):
    """-> (datetime or date, all_day) in local naive time."""

    value = value.strip()

    if "VALUE=DATE" in params or re.fullmatch(r"\d{8}", value):
        return datetime.strptime(value[:8], "%Y%m%d").date(), True

    if value.endswith("Z"):
        moment = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return moment.astimezone().replace(tzinfo=None), False

    moment = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    tz = re.search(r"TZID=([^;:]+)", params)

    if tz:
        try:
            from zoneinfo import ZoneInfo

            return moment.replace(tzinfo=ZoneInfo(tz.group(1))).astimezone().replace(tzinfo=None), False
        except Exception:  # noqa: BLE001
            pass

    return moment, False


DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]


def _occurs(start_day: date, rule: str, day: date, until=None) -> bool:
    """Daily / weekly / monthly / yearly repeats, which cover almost every calendar entry."""

    if day < start_day:
        return False

    parts = dict(p.split("=", 1) for p in rule.split(";") if "=" in p)

    if "COUNT" in parts:          # bounded series are rare; skip rather than guess
        return False

    if until and day > until:
        return False

    interval = int(parts.get("INTERVAL", 1))
    freq = parts.get("FREQ")
    delta = (day - start_day).days

    if freq == "DAILY":
        return delta % interval == 0

    if freq == "WEEKLY":
        days = parts.get("BYDAY", DAYS[start_day.weekday()]).split(",")
        days = [re.sub(r"[+-]?\d+", "", d) for d in days]

        return DAYS[day.weekday()] in days and (delta // 7) % interval == 0

    if freq == "MONTHLY":
        return day.day == start_day.day and ((day.year - start_day.year) * 12 + day.month - start_day.month) % interval == 0

    if freq == "YEARLY":
        return (day.month, day.day) == (start_day.month, start_day.day)

    return False


def events_on(text: str, day: date) -> list:
    """[(time or None, title)] for `day`, sorted. Handles plain and simple repeating events."""

    events = []
    block = None

    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            block = {}
        elif line == "END:VEVENT" and block is not None:
            events += _event_on(block, day)
            block = None
        elif block is not None and ":" in line:
            head, value = line.split(":", 1)
            name = head.split(";", 1)[0].upper()
            block.setdefault(name, (head, value))

    return sorted(events, key=lambda e: (e[0] is not None, e[0] or time(0), e[1]))


def _event_on(block, day):
    try:
        head, value = block["DTSTART"]
        start, all_day = _parse_dt(value, head)
        title = block.get("SUMMARY", ("", "Busy"))[1].replace("\\,", ",").replace("\\;", ";").strip() or "Busy"
        start_day = start if all_day else start.date()

        if "RRULE" in block:
            until = None
            m = re.search(r"UNTIL=(\d{8})", block["RRULE"][1])

            if m:
                until = datetime.strptime(m.group(1), "%Y%m%d").date()

            hit = _occurs(start_day, block["RRULE"][1], day, until)
        else:
            end_day = start_day

            if all_day and "DTEND" in block:
                end_day = _parse_dt(block["DTEND"][1], block["DTEND"][0])[0] - timedelta(days=1)

            hit = start_day <= day <= end_day

        if hit and block.get("STATUS", ("", ""))[1].upper() != "CANCELLED":
            return [(None if all_day else start.time(), title)]

    except Exception:  # noqa: BLE001
        logger.debug("Skipped an unreadable calendar event.", exc_info=True)

    return []


def load_calendar(source: str, fetch=None):
    """Text of an .ics file path or https URL (Google Calendar's 'secret address in iCal format'), or None."""

    if not source:
        return None

    try:
        if source.lower().startswith("https://"):
            fetch = fetch or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Torque"}), timeout=8).read().decode("utf-8", "replace"))
            return fetch(source)

        with open(source, encoding="utf-8", errors="replace") as file:
            return file.read()

    except Exception:  # noqa: BLE001
        logger.debug("Calendar unavailable.", exc_info=True)
        return None
