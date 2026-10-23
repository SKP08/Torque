import re

from torque.system.system_commands import (
    STRONG_CLOSE,
    STRONG_OPEN,
    WEAK_CLOSE,
    WEAK_OPEN,
)

_ALL_VERBS = STRONG_OPEN + WEAK_OPEN + STRONG_CLOSE + WEAK_CLOSE
_STRONG_VERBS = set(STRONG_OPEN + STRONG_CLOSE)

_VERB_ALTERNATION = "|".join(_ALL_VERBS)

_PREAMBLE = re.compile(
    r"^(?:(?:please|hey|ok|okay|just|can you|could you|would you|will you|"
    r"i want you to|i want to|i need you to|let's|lets|go ahead and)\b[\s,]*)+"
)

# "open edge and then open chrome", "close notepad then start spotify"
_SEPARATOR = re.compile(
    rf"\s+(?:and then|then|and|also)\s+(?=(?:{_VERB_ALTERNATION})\b)"
)

_LEADING_FILLER = re.compile(r"^(?:up|the|my|a|an)\s+")
_TRAILING_FILLER = re.compile(
    r"\s+(?:app|application|program|please|for me|now|thanks|thank you|"
    r"yeah|okay|ok|right)$"
)

# Whisper often drops punctuation: "open edge open file explorer".
# Split before a strong verb unless the previous word makes it part of a
# phrase ("close the open window").
_NO_SPLIT_AFTER = {"the", "a", "an", "my", "to", "of", "and", "or", "please", "then"}


class SystemRouter:
    """
    Parses spoken text into app commands.

    route() returns None (not a command), a single command dict, or
    {"action": "sequence", "commands": [...]}. Each command is
    {"action": "open"|"close", "target": str, "explicit": bool}; see
    system_commands.py for what "explicit" means.
    """

    OPEN_COMMANDS = STRONG_OPEN + WEAK_OPEN
    CLOSE_COMMANDS = STRONG_CLOSE + WEAK_CLOSE

    def _clean(self, text: str) -> str:

        if not text:
            return ""

        text = text.lower().strip()
        text = re.sub(r"[.!?;:]", " ", text)
        text = re.sub(r"\s*,\s*", ", ", text)
        text = re.sub(r"\s+", " ", text)

        return text.strip(" ,")

    def _clean_target(self, target: str) -> str:

        target = target.strip(" ,")

        changed = True

        while changed:

            changed = False

            for pattern in (_LEADING_FILLER, _TRAILING_FILLER):

                cleaned = pattern.sub("", target).strip(" ,")

                if cleaned != target:
                    target = cleaned
                    changed = True

        return target

    def _split_inline(self, part: str) -> list[str]:

        pieces = []
        current = []

        for token in part.split():

            if (
                current
                and token in _STRONG_VERBS
                and len(current) >= 2
                and current[-1] not in _NO_SPLIT_AFTER
            ):
                pieces.append(" ".join(current))
                current = []

            current.append(token)

        if current:
            pieces.append(" ".join(current))

        return pieces

    def _split_commands(self, text: str) -> list[str]:

        parts = []

        for comma_part in text.split(","):

            comma_part = comma_part.strip()

            if not comma_part:
                continue

            for chunk in _SEPARATOR.split(comma_part):
                parts.extend(self._split_inline(chunk.strip()))

        return parts

    def _match_command(self, text: str):

        text = _PREAMBLE.sub("", text.strip()).strip()

        if not text:
            return None

        verb, _, rest = text.partition(" ")

        if verb in STRONG_OPEN + WEAK_OPEN:
            action = "open"
        elif verb in STRONG_CLOSE + WEAK_CLOSE:
            action = "close"
        else:
            return None

        target = self._clean_target(rest)

        if not target:
            return None

        return {
            "action": action,
            "target": target,
            "explicit": verb in _STRONG_VERBS,
        }

    def route(self, text: str):

        text = self._clean(text)

        if not text:
            return None

        commands = []

        for part in self._split_commands(text):

            command = self._match_command(part)

            if command:
                commands.append(command)

        if not commands:
            return None

        if len(commands) == 1:
            return commands[0]

        return {
            "action": "sequence",
            "commands": commands,
        }
