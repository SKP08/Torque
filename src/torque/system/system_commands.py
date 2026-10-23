from dataclasses import dataclass

# "Strong" verbs are an explicit instruction to control an app: if the app
# can't be found Torque says so. "Weak" verbs are also ordinary English
# ("start talking", "run a test", "quit smoking"), so they only act when a
# real application matches; otherwise the request falls through to the LLM.
STRONG_OPEN = ("open", "launch")
WEAK_OPEN = ("start", "run")

STRONG_CLOSE = ("close",)
WEAK_CLOSE = ("quit", "exit")

OPEN_VERBS = STRONG_OPEN + WEAK_OPEN
CLOSE_VERBS = STRONG_CLOSE + WEAK_CLOSE
COMMAND_VERBS = OPEN_VERBS + CLOSE_VERBS


@dataclass
class ActionResult:
    """Outcome of an action Torque performed on the computer."""

    success: bool
    message: str
