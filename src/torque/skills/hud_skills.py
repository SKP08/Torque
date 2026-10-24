import re

from torque.hud.status import NetworkRate, spoken_status, system_status
from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult


def build_hud_skills(probe=None, status_fn=None, timers=None):
    """Skills whose answer is partly on screen: the status HUD and dismiss."""

    rate = NetworkRate()
    rate.read()                                   # first sample, so the second has a rate

    def status(_):
        data = status_fn() if status_fn else system_status(probe=probe, rate=rate)

        if timers is not None:
            data = {**data, "timers": [{"label": t["label"] or t["kind"], "seconds": int(timers.remaining(t))}
                                       for t in timers.active()[:4]]}

        return ActionResult(True, spoken_status(data), hud=data)

    def dismiss(_):
        return ActionResult(True, "Of course.", hud={"kind": "clear"})

    pc = r"(?:my |the )?(?:pc|computer|laptop|machine|system)"

    rules = [
        ("status", rf"(?:(?:give me |show me |run )?(?:a |the )?(?:system |full )?status(?: report| check)?|"
                   rf"(?:run |show )?(?:a |the )?(?:system )?diagnostics?|"
                   rf"how(?:'s| is) {pc}(?: doing| running| holding up)?|(?:check|report) on {pc})$", status),
        ("dismiss", r"(?:dismiss|clear|hide|close)(?: (?:that|this|it|all|everything))?$|"
                    r"(?:dismiss|clear|hide|close) (?:the )?(?:panels?|hud|display|overlay|screen)$", dismiss),
    ]

    return [Skill(name, SAFE, re.compile(pattern), action) for name, pattern, action in rules]
