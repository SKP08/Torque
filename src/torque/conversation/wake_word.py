"""Spotting "Hey Torque" in a transcript.

Wake detection runs on Whisper's transcript of each speech segment, so the
matcher has to forgive the ways Whisper mishears a name like "Torque"
("Tork", "Torch", "Torque's" ...). Matching is anchored to the START of the
utterance, which keeps ordinary sentences about engines ("the torque on
this bolt is...") from waking the assistant.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

GREETINGS = {"hey", "hay", "hi", "hello", "ok", "okay", "yo", "hei"}
FILLERS = {"um", "uh", "uhh", "umm", "oh", "ah", "er"}

# Wakes the assistant even without a greeting ("Torque, what's the time").
STRONG = {"torque", "torq", "torc", "torqe", "torqu", "tourque", "torke", "torqued"}

# Common mishearings that are real words: only count after "hey"/"ok".
WEAK = {"tork", "torch", "tor", "tourk", "taurk", "dork", "tark", "turk", "tauk"}

_TOKEN = re.compile(r"[A-Za-z']+")

_LEADING_PUNCTUATION = " \t\n,.!?:;-—…"


@dataclass(frozen=True)
class WakeMatch:
    matched: bool
    remainder: str = ""
    greeted: bool = False


NO_MATCH = WakeMatch(False)


def _normalise(token: str) -> str:

    token = token.lower().replace("'", "")

    # "torque's" -> "torque"
    if token.endswith("s") and token[:-1] in STRONG:
        token = token[:-1]

    return token


def _is_strong(token: str) -> bool:

    if token in STRONG:
        return True

    # Close spellings ("torques", "torgue") - only for longer tokens so
    # short ordinary words are never pulled in.
    return len(token) >= 5 and fuzz.ratio(token, "torque") >= 80


def match_wake_word(text: str) -> WakeMatch:
    """
    Does `text` start with the wake word? Returns the match and whatever
    was said after it (so "Hey Torque, open Chrome" can be acted on at once).
    """

    if not text:
        return NO_MATCH

    tokens = list(_TOKEN.finditer(text))

    index = 0

    while index < len(tokens) and _normalise(tokens[index].group()) in FILLERS:
        index += 1

    greeted = False

    if index < len(tokens) and _normalise(tokens[index].group()) in GREETINGS:
        greeted = True
        index += 1

    if index >= len(tokens):
        return NO_MATCH

    candidate = tokens[index]
    word = _normalise(candidate.group())

    if _is_strong(word) or (greeted and word in WEAK):

        remainder = text[candidate.end():].lstrip(_LEADING_PUNCTUATION)

        return WakeMatch(True, remainder.strip(), greeted)

    return NO_MATCH
