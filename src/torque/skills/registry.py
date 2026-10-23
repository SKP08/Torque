import re
import time

from loguru import logger

from torque.skills.base import CONFIRM

_PREAMBLE = re.compile(
    r"^(?:(?:please|hey|ok|okay|just|can you|could you|would you|will you|"
    r"i want you to|i want to|i need you to|let's|lets|go ahead and|torque)\b[\s,]*)+"
)

_YES = re.compile(
    r"^(?:yes|yeah|yep|yup|sure|confirm|confirmed|do it|go ahead|please do|"
    r"affirmative|correct|ok do it|okay do it)\b"
)
_NO = re.compile(r"^(?:no|nope|nah|cancel|stop|don't|do not|never mind|nevermind|abort)\b")


def normalise(text: str) -> str:

    text = (text or "").lower().strip()
    text = re.sub(r"[.!?;:,]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return _PREAMBLE.sub("", text).strip()


class SkillRegistry:
    """
    Finds the skill for a request and enforces the permission tier.

    A CONFIRM skill is not run when asked for: Torque asks first and keeps it
    pending. The next thing said decides: "yes" runs it, anything else
    cancels it (so an unrelated sentence can never trigger it later).
    """

    CONFIRM_TTL = 30.0      # seconds a pending confirmation stays valid

    def __init__(self, skills, clock=time.monotonic):

        self.skills = list(skills)
        self._clock = clock
        self._pending = None          # (skill, match, expires_at)

    @property
    def awaiting_confirmation(self) -> bool:

        return self._pending is not None and self._clock() < self._pending[2]

    REMOTE_REFUSAL = "That one needs you at the PC."

    def handle(self, text: str, allow_confirm: bool = True) -> str | None:
        """
        What to say, or None if this isn't a PC-control request.

        allow_confirm=False is for requests from the phone: CONFIRM-tier
        skills (power) are refused outright, and a confirmation pending on
        the PC can't be answered from the phone.
        """

        said = normalise(text)

        if self._pending and allow_confirm:
            reply = self._resolve_pending(said)

            if reply:
                return reply

        if not said:
            return None

        for skill in self.skills:

            match = skill.match(said)

            if not match:
                continue

            if skill.tier == CONFIRM:

                if not allow_confirm:
                    return self.REMOTE_REFUSAL

                self._pending = (skill, match, self._clock() + self.CONFIRM_TTL)

                logger.info(f"Skill '{skill.name}' waiting for confirmation.")

                return skill.prompt

            logger.info(f"Skill '{skill.name}'")

            return skill.run(match).message

        return None

    def _resolve_pending(self, said: str) -> str | None:

        skill, match, expires = self._pending

        self._pending = None            # one chance only

        if self._clock() >= expires:
            return None

        if _YES.match(said):

            logger.info(f"Skill '{skill.name}' confirmed.")

            return skill.run(match).message

        if _NO.match(said):
            return "Okay, cancelled."

        return None                      # something else: drop it, handle normally
