import re

from torque.desktop.context import active_window
from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult


def build_context_skills(context_fn=active_window):
    """Questions about the active window; answered locally, no model needed."""

    def current(_):
        ctx = context_fn()

        return ActionResult(True, ctx.spoken() if ctx else "I can't tell which window is active.")

    pattern = re.compile(
        r"(?:what|which) (?:app|application|program|window)(?: am i| is)(?: in| using| on| active| open| focused)?(?: right now)?$|"
        r"what(?:'s| is) (?:the )?(?:active|current|focused|front) (?:app|window|application|program)$|"
        r"what am i (?:working on|doing)(?: right now)?$|where am i$"
    )

    return [Skill("active_window", SAFE, pattern, current)]
