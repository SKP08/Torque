import re

from torque.skills.base import SAFE, Skill
from torque.system.system_commands import ActionResult


def build_push_skills(pusher):
    """'send a test to my phone'. `pusher` is None when phone alerts aren't set up."""

    def test(_):
        if pusher is None:
            return ActionResult(False, "Phone alerts are off. Set push_enabled and a push_topic in settings.local.json, then subscribe to that topic in the ntfy app.")

        pusher.post_ok = pusher.send("This is a test alert from Torque.", "info", force=True)

        return ActionResult(True, "Sent a test alert to your phone." if pusher.post_ok else "I already sent that a moment ago.")

    return [Skill("push_test", SAFE,
                  re.compile(r"(?:send|push) (?:a )?(?:test )?(?:alert|notification|message)(?: test)? to my phone$|test (?:my )?phone (?:alerts|notifications)$"),
                  test)]
