"""
Voice control of the desktop: click things by the words on them, type, scroll.

Off by default (desktop_control_enabled). Each command does ONE thing and then
stops; there is no autonomous loop. Local only: refused when the request comes
from the phone. Clicking something labelled like a purchase or deletion needs a
spoken "yes" first, and typing always does.
"""

import re

from torque.agent.browser_tools import RISKY_CLICK
from torque.desktop.backend import ALLOWED_KEYS
from torque.skills.base import CONFIRM, SAFE, Skill
from torque.system.system_commands import ActionResult

_LABEL = r"(?:on |the |a |an )*(?P<label>[a-z0-9][a-z0-9 .'&+-]{0,60}?)(?: (?:button|link|icon|tab|option|menu|field|text|box))?"
_RISKY_WORDS = RISKY_CLICK.pattern


def build_desktop_skills(finder, desktop):

    def click_label(label, **kw):
        label = (label or "").strip()
        targets = finder.find(label)

        if not targets:
            return ActionResult(False, f"I can't see '{label}' on the screen.")

        target = targets[0]
        desktop.click(target.x, target.y, **kw)

        return ActionResult(True, "Done.")

    def click(m):
        return click_label(m.group("label"))

    def double_click(m):
        return click_label(m.group("label"), double=True)

    def right_click(m):
        return click_label(m.group("label"), button="right")

    def type_text(m):
        text = m.group("text").strip()
        desktop.type_text(text)

        return ActionResult(True, "Typed.")

    def press(m):
        key = m.group("key").strip()

        if key not in ALLOWED_KEYS:
            return ActionResult(False, f"I don't press {key} by voice.")

        desktop.press(key)

        return ActionResult(True, "Done.")

    def scroll(m):
        down = m.group("dir") == "down"
        desktop.scroll(-5 if down else 5)

        return ActionResult(True, "Done.")

    keys = "|".join(sorted((re.escape(k) for k in ALLOWED_KEYS), key=len, reverse=True))

    rules = [
        # risky labels are caught first and need a "yes"
        Skill("click_risky", CONFIRM,
              re.compile(rf"(?:click|press|tap|hit|select) (?=.*(?:{_RISKY_WORDS}))" + _LABEL + "$"), click,
              prompt="That could spend money, send something or delete something. Should I click it?",
              local_only=True),
        Skill("double_click", SAFE, re.compile(rf"double click {_LABEL}$"), double_click, local_only=True),
        Skill("right_click", SAFE, re.compile(rf"right click {_LABEL}$"), right_click, local_only=True),
        Skill("type", CONFIRM, re.compile(r"type (?P<text>.+)$"), type_text,
              prompt="I'll type that into whichever window is active. Go ahead?", local_only=True),
        Skill("press_key", SAFE, re.compile(rf"press (?P<key>{keys})(?: key)?$"), press, local_only=True),
        Skill("click", SAFE, re.compile(rf"(?:click|tap|select|press) {_LABEL}$"), click, local_only=True),
        Skill("scroll", SAFE, re.compile(r"scroll (?P<dir>up|down)$"), scroll, local_only=True),
    ]

    return rules
