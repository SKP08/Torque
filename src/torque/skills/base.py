from dataclasses import dataclass

from torque.system.system_commands import ActionResult

SAFE = "safe"          # runs immediately
CONFIRM = "confirm"    # Torque asks, and only runs after a spoken "yes"


@dataclass
class Skill:
    """
    One thing Torque can do on the PC.

    name     short id, used in logs
    tier     SAFE or CONFIRM (anything hard to undo)
    pattern  compiled regex matched against the normalised request
    action   callable(match) -> ActionResult
    prompt   for CONFIRM skills: what Torque asks before doing it
    local_only  never run for phone requests (desktop control)
    """

    name: str
    tier: str
    pattern: object
    action: object
    prompt: str = ""
    local_only: bool = False      # refused when the request comes from the phone

    def match(self, text: str):
        return self.pattern.match(text)

    def run(self, match) -> ActionResult:

        try:
            return self.action(match)

        except NotImplementedError:
            return ActionResult(False, "That only works on Windows.")

        except Exception:  # noqa: BLE001
            from loguru import logger

            logger.exception(f"Skill '{self.name}' failed.")

            return ActionResult(False, "I couldn't do that.")
