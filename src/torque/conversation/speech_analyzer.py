import re
from typing import ClassVar

from loguru import logger

from torque.system.system_commands import COMMAND_VERBS

_VERB_START = re.compile(r"^(?:" + "|".join(COMMAND_VERBS) + r")\b")
_WAKE_WORD = re.compile(r"^(?:(?:hey|ok|okay)\s+)?torque\b[\s,.!:;-]*")


class SpeechAnalyzer:

    # Hesitation sounds.
    FILLER_WORDS: ClassVar[set[str]] = {
        "um", "umm", "uh", "uhh", "hmm", "hmmm", "er", "err",
    }

    # Phrases that can mean the speaker is changing their mind. They are
    # only ACTED ON when what follows is itself a command ("open edge,
    # actually open chrome"); otherwise the sentence is left alone, so
    # "I'd rather use Python" or "explain it, actually, simply" survive.
    CORRECTION_WORDS: ClassVar[set[str]] = {
        "actually", "wait", "sorry", "rather", "instead", "correction",
        "i mean", "what i mean", "no wait", "no actually", "no sorry",
    }

    # Words that can trail a spoken COMMAND without being part of it.
    TRAILING_CONVERSATIONAL_WORDS: ClassVar[set[str]] = {
        "yeah", "yes", "yep", "yup", "okay", "ok", "right", "exactly",
        "sure", "fine", "thanks", "thank you", "got it", "understood",
        "please",
    }

    # A sentence that ends on one of these is probably unfinished.
    # (Deliberately narrow: "what is that" / "what is it for" are complete.)
    CONTINUATION_WORDS: ClassVar[set[str]] = {
        "and", "or", "but", "because", "if", "when", "with", "to", "from",
        "than", "which",
    }

    ACKNOWLEDGEMENTS: ClassVar[set[str]] = {
        "yeah", "yes", "yep", "yup", "okay", "ok", "right", "exactly",
        "sure", "fine", "got it", "understood", "mm", "hmm", "uh huh",
    }

    # ----------------------------------------------------------

    def normalize(self, text: str) -> str:

        if not text:
            return ""

        return re.sub(r"\s+", " ", text.strip().lower())

    def words(self, text: str) -> list[str]:
        return self.normalize(text).split()

    def contains_filler(self, text: str) -> bool:
        return any(word.strip(".,!?") in self.FILLER_WORDS for word in self.words(text))

    def _correction_spans(self, normalized: str) -> list[tuple[int, int]]:

        phrases = sorted(self.CORRECTION_WORDS, key=len, reverse=True)

        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(p) for p in phrases) + r")\b"
        )

        return [(m.start(), m.end()) for m in pattern.finditer(normalized)]

    def contains_correction(self, text: str) -> bool:
        return bool(self._correction_spans(self.normalize(text)))

    @staticmethod
    def starts_with_command(text: str) -> bool:
        return bool(_VERB_START.match(text.strip().lower()))

    # ----------------------------------------------------------

    def _strip_leading_noise(self, text: str) -> str:
        """Drop punctuation, fillers and stacked correction words."""

        text = text.lstrip(" ,.!?;:-")

        changed = True

        while changed:

            changed = False

            for word in (*self.FILLER_WORDS, "no", "sorry", "wait", "actually"):

                match = re.match(rf"{re.escape(word)}\b[\s,.!?;:-]*", text)

                if match:
                    text = text[match.end():]
                    changed = True

        return text.strip()

    def _remove_trailing_conversation(self, text: str) -> str:

        phrases = sorted(self.TRAILING_CONVERSATIONAL_WORDS, key=len, reverse=True)

        changed = True

        while changed and text:

            changed = False

            for phrase in phrases:

                match = re.search(rf"(?:^|[\s,]+){re.escape(phrase)}[\s.!?]*$", text)

                if match:

                    candidate = text[:match.start()].strip(" ,")

                    if not candidate:
                        return text

                    text = candidate
                    changed = True
                    break

        return text

    def extract_corrected_text(self, text: str) -> str:
        """
        Return the text a router should act on.

        - strips a leading "Torque," wake word
        - if the user corrects themselves into a new command, the last
          command wins ("open edge actually open chrome" -> "open chrome")
        - trailing chatter is removed from commands only ("open edge yeah")
        - anything that isn't a command is returned unchanged (apart from
          normalisation), so ordinary sentences are never cut up
        """

        normalized = self.normalize(text)

        if not normalized:
            return ""

        normalized = _WAKE_WORD.sub("", normalized).strip()

        for _, end in reversed(self._correction_spans(normalized)):

            remainder = self._strip_leading_noise(normalized[end:])

            if self.starts_with_command(remainder):

                logger.debug(f"Correction: '{normalized}' -> '{remainder}'")

                normalized = remainder
                break

        if self.starts_with_command(normalized):
            normalized = self._remove_trailing_conversation(normalized)

        return normalized.rstrip(" ,.!?;:").strip()

    # ----------------------------------------------------------

    def appears_incomplete(self, text: str) -> bool:

        words = self.words(text)

        if len(words) < 2:
            return False

        return words[-1].strip(".,!?;:") in self.CONTINUATION_WORDS

    def is_short_acknowledgement(self, text: str) -> bool:
        return self.normalize(text).strip(" .,!?") in self.ACKNOWLEDGEMENTS

    def word_count(self, text: str) -> int:
        return len(self.words(text))

    def analyze(self, text: str) -> dict:

        normalized = self.normalize(text)

        return {
            "text": normalized,
            "has_filler": self.contains_filler(normalized),
            "has_correction": self.contains_correction(normalized),
            "appears_incomplete": self.appears_incomplete(normalized),
            "short_acknowledgement": self.is_short_acknowledgement(normalized),
            "word_count": self.word_count(normalized),
        }
