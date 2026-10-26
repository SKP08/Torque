"""Builds the spoken morning briefing from whatever sources are available."""

import re
from datetime import datetime, timedelta

from loguru import logger

from torque.briefing import sources
from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult


def greeting(now: datetime, name: str = "") -> str:
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 17 else "evening"

    return f"Good {part}, {name}." if name else f"Good {part}."


def say_time(t) -> str:
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"

    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"


class Briefing:
    """All parts optional: weather (config city/lat/lon), calendar (.ics path or URL), timers, yesterday's journal."""

    def __init__(self, config=None, timers=None, journal=None, weather=sources.fetch_weather,
                 calendar=sources.load_calendar, clock=datetime.now, name=""):
        self.config = config or {}
        self.timers = timers
        self.journal = journal
        self.weather = weather
        self.calendar = calendar
        self.clock = clock
        self.name = name

    def build(self) -> list:
        now = self.clock()
        lines = [greeting(now, self.name or self.config.get("user_name", "")), f"It's {now.strftime('%A')}, {now.day} {now.strftime('%B')}."]

        for part in (self._weather, self._calendar, self._timers, self._yesterday):
            try:
                text = part(now)
            except Exception:  # noqa: BLE001
                logger.debug("Briefing part failed.", exc_info=True)
                text = None

            if text:
                lines.append(text)

        return lines

    def _weather(self, now):
        c = self.config
        w = self.weather(c.get("briefing_city", ""), c.get("briefing_lat"), c.get("briefing_lon"))

        if not w:
            return None

        text = f"It's {w['temp']} degrees{' and ' + w['sky'] if w['sky'] else ''}"
        text += f"{' in ' + w['place'] if w.get('place') else ''}, with a high of {w['high']} and a low of {w['low']}."

        if w["rain"] >= 40:
            text += f" There's a {w['rain']} percent chance of rain, so take an umbrella."

        return text

    def _calendar(self, now):
        text = self.calendar(self.config.get("briefing_calendar", ""))

        if text is None:
            return None

        events = sources.events_on(text, now.date())

        if not events:
            return "Your calendar is clear today."

        shown = [f"{title} at {say_time(t)}" if t else f"{title} all day" for t, title in events[:4]]
        more = f", and {len(events) - 4} more" if len(events) > 4 else ""
        count = "one event" if len(events) == 1 else f"{len(events)} events"

        return f"You have {count} today: " + "; ".join(shown) + more + "."

    def _timers(self, now):
        if not self.timers:
            return None

        items = [i for i in self.timers.active() if i.get("kind") == "reminder"]

        if not items:
            return None

        labels = [i.get("label") or "a reminder" for i in items[:3]]

        return "Reminders: " + ", ".join(labels) + "."

    def _yesterday(self, now):
        if not self.journal:
            return None

        text = self.journal.summary(now.date() - timedelta(days=1))

        return f"Yesterday: {text.strip()}" if text else None


def build_briefing_skills(briefing):
    """'good morning' alone is a greeting, so require a clear ask."""

    pattern = re.compile(r"(?:give me |read me |play |start )?(?:my |the )?(?:morning |daily |day )?(?:briefing|brief|rundown|summary of my day)$"
                         r"|brief me$|what(?:'s| is) (?:on )?(?:my )?(?:day|today) (?:looking )?like$|what do i have today$|what(?:'s| is) my day$")

    def action(_):
        return ActionResult(True, " ".join(briefing.build()))

    return [Skill("briefing", SAFE, pattern, action)]


class BriefingScheduler:
    """Gives the briefing once a day, the first time Torque is running after `at` (HH:MM),
    unless it is already later than `at` + `window_hours`. The date is saved so a restart doesn't repeat it."""

    def __init__(self, briefing, state_path, at="08:00", window_hours=4, clock=datetime.now):
        self.briefing = briefing
        self.state_path = state_path
        self.clock = clock
        self.window_hours = window_hours

        try:
            hour, minute = (int(x) for x in at.split(":"))
            self.at = (hour, minute)
        except (ValueError, AttributeError):
            self.at = (8, 0)

    def _last(self):
        try:
            with open(self.state_path, encoding="utf-8") as file:
                return file.read().strip()
        except OSError:
            return ""

    def due(self) -> bool:
        now = self.clock()
        start = now.replace(hour=self.at[0], minute=self.at[1], second=0, microsecond=0)

        if not (start <= now <= start + timedelta(hours=self.window_hours)):
            return False

        return self._last() != now.date().isoformat()

    def run(self, announce) -> bool:
        """Say it now if due. True if a briefing was given."""

        if not self.due():
            return False

        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(self.clock().date().isoformat(), encoding="utf-8")
        except OSError:
            logger.debug("Could not save briefing state.", exc_info=True)

        announce(" ".join(self.briefing.build()), "info", True)

        return True
