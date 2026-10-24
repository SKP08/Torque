import re

from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult
from torque.timers.store import _NUMBER, _UNIT, parse_duration, spoken_duration

# A duration phrase: "5 minutes", "an hour and a half", "1 hour 30 minutes", "half an hour".
_DUR = (rf"(?P<d>(?:(?:{_NUMBER}|half an?|and a half|and)\s+)*(?:{_UNIT})\b"
        rf"(?:\s+(?:and a half|and)?\s*(?:(?:{_NUMBER})\s+)?(?:{_UNIT})?\b)*)")


def build_timer_skills(store):
    """Timers and reminders. Due ones are announced by the AlertWatcher."""

    def _duration(match):
        seconds = parse_duration(match.group("d"))

        return seconds

    def set_timer(m):
        seconds = _duration(m)

        if not seconds:
            return ActionResult(False, "How long should the timer be?")

        store.add(seconds, m.groupdict().get("label") or "", "timer")
        return ActionResult(True, f"Timer set for {spoken_duration(seconds)}.")

    def remind(m):
        seconds = _duration(m)
        what = re.sub(r"^(?:to|that)\s+", "", (m.group("what") or "").strip())

        if not seconds:
            return ActionResult(False, "When should I remind you?")

        if not what:
            return ActionResult(False, "What should I remind you about?")

        store.add(seconds, what, "reminder")
        return ActionResult(True, f"I'll remind you in {spoken_duration(seconds)}.")

    def status(_):
        items = store.active()

        if not items:
            return ActionResult(True, "You have no timers or reminders running.")

        parts = []

        for i in items[:4]:
            name = i["label"] or "timer"
            parts.append(f"{name}, {spoken_duration(store.remaining(i))} left")

        return ActionResult(True, "; ".join(parts) + ".")

    def cancel(_):
        n = store.cancel()

        return ActionResult(True, "Cancelled." if n else "There was nothing to cancel.")

    rules = [
        ("timer_set", rf"(?:set |start |create )?(?:a |an )?(?:(?P<label>[a-z ]+?) )?timer (?:for|of) {_DUR}$", set_timer),
        ("remind_in", rf"remind me in {_DUR} (?P<what>(?:to|that) .+)$", remind),
        ("remind_to", rf"remind me (?P<what>(?:to|that) .+?) in {_DUR}$", remind),
        ("timer_status", r"(?:how (?:long|much time) (?:is )?left(?: on (?:the |my )?timer)?|"
                         r"what(?:'s| is| are) (?:my |the )?(?:timers?|reminders?)(?: running| left)?|"
                         r"(?:list|show) (?:my |the )?(?:timers?|reminders?)|check (?:my |the )?timers?)$", status),
        ("timer_cancel", r"(?:cancel|stop|clear|delete|remove) (?:all |my |the )?(?:timers?|reminders?|alarms?)$", cancel),
    ]

    return [Skill(name, SAFE, re.compile(pattern), action) for name, pattern, action in rules]
