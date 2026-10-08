import re
from typing import ClassVar

from loguru import logger


class SpeechAnalyzer:

    # Words that commonly indicate hesitation or thinking.
    FILLER_WORDS: ClassVar[set[str]] = {
        "um",
        "umm",
        "uh",
        "uhh",
        "hmm",
        "hmmm",
        "er",
        "err",
    }

    # Words/phrases that can indicate the speaker is changing
    # or correcting their previous thought.
    CORRECTION_WORDS: ClassVar[set[str]] = {
        "actually",
        "wait",
        "sorry",
        "rather",
        "instead",
        "correction",
        "i mean",
        "what i mean",
        "no wait",
        "no actually",
    }

    # Conversational words that may appear at the end of speech
    # but normally aren't part of the actual command.
    TRAILING_CONVERSATIONAL_WORDS: ClassVar[set[str]] = {
        "yeah",
        "yes",
        "yep",
        "yup",
        "okay",
        "ok",
        "right",
        "exactly",
        "sure",
        "fine",
        "thanks",
        "thank you",
        "got it",
        "understood",
    }

    # Words that suggest the sentence may continue.
    CONTINUATION_WORDS: ClassVar[set[str]] = {
        "and",
        "or",
        "but",
        "because",
        "so",
        "then",
        "if",
        "when",
        "which",
        "that",
        "with",
        "for",
        "to",
        "from",
        "about",
        "under",
        "over",
        "than",
    }

    ACKNOWLEDGEMENTS: ClassVar[set[str]] = {
        "yeah",
        "yes",
        "yep",
        "yup",
        "okay",
        "ok",
        "right",
        "exactly",
        "sure",
        "fine",
        "got it",
        "understood",
    }

    def normalize(self, text: str) -> str:

        if not text:
            return ""

        text = text.strip().lower()

        text = re.sub(r"\s+", " ", text)

        return text

    def words(self, text: str) -> list[str]:

        normalized = self.normalize(text)

        return normalized.split()

    def contains_filler(self, text: str) -> bool:

        words = self.words(text)

        return any(
            word in self.FILLER_WORDS
            for word in words
        )

    def contains_correction(self, text: str) -> bool:

        normalized = self.normalize(text)

        # Check multi-word correction phrases first.
        correction_phrases = sorted(
            (
                phrase
                for phrase in self.CORRECTION_WORDS
                if " " in phrase
            ),
            key=len,
            reverse=True,
        )

        for phrase in correction_phrases:

            pattern = rf"\b{re.escape(phrase)}\b"

            if re.search(pattern, normalized):
                return True

        # Check single-word correction markers.
        words = set(self.words(normalized))

        single_word_corrections = {
            word
            for word in self.CORRECTION_WORDS
            if " " not in word
        }

        return bool(
            words.intersection(
                single_word_corrections
            )
        )

    def _remove_trailing_conversation(
        self,
        text: str,
    ) -> str:
        """
        Remove conversational acknowledgements that appear
        at the very end of a command.

        Examples:

            "open edge yeah"
                -> "open edge"

            "open edge okay"
                -> "open edge"

            "open edge yeah thanks"
                -> "open edge"

            "open edge"
                -> "open edge"

        Important:
        We only remove these words when they occur at the
        END of the request. We do not remove them from the
        middle of a sentence.
        """

        normalized = self.normalize(text)

        if not normalized:
            return ""

        # Long phrases first.
        trailing_phrases = sorted(
            self.TRAILING_CONVERSATIONAL_WORDS,
            key=len,
            reverse=True,
        )

        changed = True

        while changed and normalized:

            changed = False

            for phrase in trailing_phrases:

                pattern = (
                    rf"(?:^|\s)"
                    rf"{re.escape(phrase)}"
                    rf"\s*$"
                )

                match = re.search(
                    pattern,
                    normalized,
                )

                if match:

                    candidate = normalized[
                        :match.start()
                    ].strip()

                    # Don't reduce a standalone acknowledgement
                    # to an empty string.
                    if not candidate:
                        return normalized

                    normalized = candidate
                    changed = True
                    break

        return normalized

    def extract_corrected_text(
        self,
        text: str,
    ) -> str:
        """
        Extract the user's final intended request.

        The function handles:

        1. Normal requests.
        2. Self-corrections.
        3. Hesitation/filler words.
        4. Trailing conversational acknowledgements.

        Examples:

            "open edge actually open chrome"
                -> "open chrome"

            "open edge wait open file explorer"
                -> "open file explorer"

            "open edge sorry open chrome"
                -> "open chrome"

            "open microsoft edge umm no sorry open file explorer"
                -> "open file explorer"

            "open final explainer yeah"
                -> "open final explainer"

            "open final explainer okay"
                -> "open final explainer"

            "open chrome"
                -> "open chrome"
        """

        normalized = self.normalize(text)

        if not normalized:
            return ""

        # ---------------------------------------------------------
        # STEP 1
        # Find correction markers.
        # ---------------------------------------------------------

        markers = []

        # Longer phrases must be checked before single words.
        phrases = sorted(
            (
                phrase
                for phrase in self.CORRECTION_WORDS
                if " " in phrase
            ),
            key=len,
            reverse=True,
        )

        for phrase in phrases:

            pattern = rf"\b{re.escape(phrase)}\b"

            for match in re.finditer(
                pattern,
                normalized,
            ):

                markers.append(
                    (
                        match.start(),
                        match.end(),
                        phrase,
                    )
                )

        # Single-word correction markers.
        single_words = {
            word
            for word in self.CORRECTION_WORDS
            if " " not in word
        }

        for word in single_words:

            pattern = rf"\b{re.escape(word)}\b"

            for match in re.finditer(
                pattern,
                normalized,
            ):

                markers.append(
                    (
                        match.start(),
                        match.end(),
                        word,
                    )
                )

        # ---------------------------------------------------------
        # STEP 2
        # If a correction exists, use the LAST correction.
        # ---------------------------------------------------------

        if markers:

            markers.sort(
                key=lambda item: item[0]
            )

            _, end_position, marker = markers[-1]

            corrected = normalized[
                end_position:
            ].strip()

            corrected = corrected.lstrip(
                " ,.!?;:-"
            ).strip()

            if corrected:

                logger.debug(
                    "Correction extracted: "
                    f"'{normalized}' → '{corrected}'"
                )

                normalized = corrected

            else:

                logger.debug(
                    "Correction detected but no text "
                    f"followed marker '{marker}'. "
                    "Keeping original input."
                )

        # ---------------------------------------------------------
        # STEP 3
        # Remove trailing conversational words.
        # ---------------------------------------------------------

        cleaned = self._remove_trailing_conversation(
            normalized
        )

        if cleaned != normalized:

            logger.debug(
                "Trailing conversation removed: "
                f"'{normalized}' → '{cleaned}'"
            )

        normalized = cleaned

        # ---------------------------------------------------------
        # STEP 4
        # Remove trailing punctuation.
        # ---------------------------------------------------------

        normalized = normalized.rstrip(
            " ,.!?;:"
        ).strip()

        return normalized

    def appears_incomplete(
        self,
        text: str,
    ) -> bool:

        words = self.words(text)

        if not words:
            return False

        last_word = words[-1].strip(
            ".,!?;:"
        )

        return last_word in self.CONTINUATION_WORDS

    def is_short_acknowledgement(
        self,
        text: str,
    ) -> bool:

        normalized = self.normalize(text)

        return normalized in self.ACKNOWLEDGEMENTS

    def word_count(
        self,
        text: str,
    ) -> int:

        return len(
            self.words(text)
        )

    def analyze(
        self,
        text: str,
    ) -> dict:

        normalized = self.normalize(text)

        if not normalized:

            return {
                "text": "",
                "has_filler": False,
                "has_correction": False,
                "appears_incomplete": False,
                "short_acknowledgement": False,
                "word_count": 0,
            }

        result = {
            "text": normalized,
            "has_filler": self.contains_filler(
                normalized
            ),
            "has_correction": self.contains_correction(
                normalized
            ),
            "appears_incomplete": self.appears_incomplete(
                normalized
            ),
            "short_acknowledgement": self.is_short_acknowledgement(
                normalized
            ),
            "word_count": self.word_count(
                normalized
            ),
        }

        logger.debug(
            f"Speech analysis: {result}"
        )

        return result