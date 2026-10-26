from datetime import date, datetime, time, timedelta

import pytest

from torque.briefing import sources
from torque.briefing.builder import Briefing, BriefingScheduler, build_briefing_skills, say_time
from torque.skills.registry import SkillRegistry

DAY = date(2026, 10, 26)           # a Monday


def ics(*events):
    return "BEGIN:VCALENDAR\r\n" + "".join("BEGIN:VEVENT\r\n" + "\r\n".join(e) + "\r\nEND:VEVENT\r\n" for e in events) + "END:VCALENDAR\r\n"


def test_events_plain_allday_and_multiday():
    text = ics(
        ["DTSTART:20261026T100000", "SUMMARY:Networks lecture"],
        ["DTSTART;VALUE=DATE:20261026", "SUMMARY:Project due"],
        ["DTSTART;VALUE=DATE:20261025", "DTEND;VALUE=DATE:20261028", "SUMMARY:Hackathon"],
        ["DTSTART:20261027T090000", "SUMMARY:Tomorrow thing"],
        ["DTSTART:20261026T150000", "SUMMARY:Lab\\, part 2", "STATUS:CANCELLED"],
    )
    assert sources.events_on(text, DAY) == [(None, "Hackathon"), (None, "Project due"), (time(10, 0), "Networks lecture")]
    assert sources.events_on(text, date(2026, 10, 28)) == []


def test_utc_events_are_converted_to_local_time(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    import time as t
    t.tzset()
    got = sources.events_on(ics(["DTSTART:20261026T043000Z", "SUMMARY:Early"]), DAY)
    assert got == [(time(10, 0), "Early")]


def test_repeating_events():
    weekly = ics(["DTSTART:20260105T093000", "RRULE:FREQ=WEEKLY;BYDAY=MO,WE", "SUMMARY:Standup"])
    assert sources.events_on(weekly, DAY) and not sources.events_on(weekly, date(2026, 10, 27))
    ended = ics(["DTSTART:20260105T093000", "RRULE:FREQ=DAILY;UNTIL=20261001", "SUMMARY:Old"])
    assert not sources.events_on(ended, DAY)
    daily = ics(["DTSTART:20261020T080000", "RRULE:FREQ=DAILY;INTERVAL=2", "SUMMARY:Pills"])
    assert sources.events_on(daily, DAY) and not sources.events_on(daily, date(2026, 10, 27))
    assert not sources.events_on(ics(["DTSTART:20260105T093000", "RRULE:FREQ=WEEKLY;COUNT=3", "SUMMARY:x"]), DAY)


def test_folded_lines_and_garbage_events():
    text = ics(["DTSTART:20261026T100000", "SUMMARY:A very long", "  title"], ["DTSTART:garbage", "SUMMARY:bad"])
    assert sources.events_on(text, DAY) == [(time(10, 0), "A very long title")]


def test_load_calendar_file_url_and_failures(tmp_path):
    f = tmp_path / "c.ics"
    f.write_text("hello")
    assert sources.load_calendar(str(f)) == "hello"
    assert sources.load_calendar(str(tmp_path / "none.ics")) is None
    assert sources.load_calendar("") is None
    assert sources.load_calendar("https://x/y.ics", fetch=lambda u: "remote") == "remote"
    def boom(u): raise OSError
    assert sources.load_calendar("https://x/y.ics", fetch=boom) is None


def test_weather_parsing_and_failure():
    calls = []
    def getter(url):
        calls.append(url)
        if "geocoding" in url:
            return {"results": [{"latitude": 28.6, "longitude": 77.2, "name": "Delhi"}]}
        return {"current": {"temperature_2m": 24.4, "weather_code": 2},
                "daily": {"temperature_2m_max": [29.2], "temperature_2m_min": [19.6], "precipitation_probability_max": [55]}}
    w = sources.fetch_weather("Delhi", getter=getter)
    assert w == {"temp": 24, "sky": "partly cloudy", "high": 29, "low": 20, "rain": 55, "place": "Delhi"}
    assert "latitude=28.6" in calls[1]
    assert sources.fetch_weather("", getter=getter) is None
    assert sources.fetch_weather("Nowhere", getter=lambda u: {"results": []}) is None
    def boom(u): raise OSError("offline")
    assert sources.fetch_weather("Delhi", getter=boom) is None
    assert sources.fetch_weather(lat=1, lon=2, getter=getter)["place"] == ""


class Timers:
    def active(self): return [{"kind": "reminder", "label": "submit assignment"}, {"kind": "timer", "label": "tea"}]


class Journal:
    def summary(self, day): return "You worked on the Torque docs feature." if day == date(2026, 10, 25) else None


def briefing(**kw):
    weather = kw.pop("weather", lambda c, a, b: {"temp": 24, "sky": "clear", "high": 29, "low": 20, "rain": 60, "place": "Delhi"})
    return Briefing({"user_name": "Shubh", "briefing_city": "Delhi", "briefing_calendar": "x"}, weather=weather,
                    calendar=kw.pop("calendar", lambda s: ics(["DTSTART:20261026T100000", "SUMMARY:Lecture"])),
                    clock=lambda: datetime(2026, 10, 26, 8, 5), **kw)


def test_full_briefing():
    text = " ".join(briefing(timers=Timers(), journal=Journal()).build())
    assert text.startswith("Good morning, Shubh. It's Monday, 26 October.")
    assert "24 degrees and clear in Delhi, with a high of 29 and a low of 20" in text and "umbrella" in text
    assert "one event today: Lecture at 10 AM" in text
    assert "Reminders: submit assignment." in text and "tea" not in text
    assert "Yesterday: You worked on the Torque docs feature." in text


def test_briefing_survives_missing_and_broken_sources():
    def boom(*a): raise RuntimeError
    text = " ".join(Briefing({}, weather=boom, calendar=boom, timers=None, journal=None, clock=lambda: datetime(2026, 10, 26, 19, 0)).build())
    assert text == "Good evening. It's Monday, 26 October."
    assert "calendar is clear" in " ".join(briefing(calendar=lambda s: ics()).build())
    assert "umbrella" not in " ".join(briefing(weather=lambda *a: {"temp": 20, "sky": "", "high": 25, "low": 15, "rain": 10, "place": ""}).build())


def test_say_time():
    assert say_time(time(0, 0)) == "12 AM" and say_time(time(13, 30)) == "1:30 PM"


def test_scheduler_gives_one_briefing_a_day_within_the_window(tmp_path):
    now = {"t": datetime(2026, 10, 26, 7, 59)}
    given = []
    s = BriefingScheduler(briefing(), tmp_path / "s.txt", "08:00", 4, clock=lambda: now["t"])
    assert not s.run(lambda *a: given.append(a))                       # too early
    now["t"] = datetime(2026, 10, 26, 9, 0)
    assert s.run(lambda *a: given.append(a)) and given[0][1:] == ("info", True)
    assert not s.run(lambda *a: given.append(a))                       # once per day
    assert not BriefingScheduler(briefing(), tmp_path / "s.txt", "08:00", clock=lambda: now["t"]).due()   # survives restart
    now["t"] = datetime(2026, 10, 27, 13, 0)
    assert not s.due()                                                 # after the window: skipped, not blurted at 1 PM
    now["t"] = datetime(2026, 10, 27, 8, 30)
    assert s.due()


def test_scheduler_bad_time_falls_back(tmp_path):
    assert BriefingScheduler(briefing(), tmp_path / "s", "banana").at == (8, 0)


@pytest.mark.parametrize("phrase,hit", [("give me my morning briefing", True), ("brief me", True), ("morning briefing", True),
                                         ("what's my day like", True), ("what do i have today", True),
                                         ("good morning", False), ("brief history of india", False), ("what is the summary", False)])
def test_briefing_skill_phrases(phrase, hit):
    reg = SkillRegistry(build_briefing_skills(briefing()))
    assert bool(reg.handle(phrase)) == hit
