import re

_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_MARKS = re.compile(r"[*_`#>~|]+")
_BULLET = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+", re.MULTILINE)
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍⭐⬆]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_SPACES = re.compile(r"\s+")


def split_sentences(text: str) -> list[str]:

    text = _SPACES.sub(" ", text or "").strip()

    if not text:
        return []

    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def clean_for_speech(text: str) -> str:
    """Strip markdown, links, bullets and emoji so text sounds natural."""

    if not text:
        return ""

    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _BULLET.sub("", text)
    text = _MD_MARKS.sub("", text)
    text = _EMOJI.sub("", text)
    text = text.replace("\n", ". ")
    text = re.sub(r"\.\s*\.", ".", text)

    return _SPACES.sub(" ", text).strip()


def to_speech(text: str, max_sentences: int = 4, max_chars: int = 500) -> str:
    """
    Turn text that was written to be read (markdown, links, bullets) into
    something short and natural to speak aloud.
    """

    sentences = split_sentences(clean_for_speech(text))

    spoken = []
    length = 0

    for sentence in sentences[:max_sentences]:

        if spoken and length + len(sentence) > max_chars:
            break

        spoken.append(sentence)
        length += len(sentence) + 1

    return " ".join(spoken).strip()


# --------------------------------------------------------------------
# Streaming: turn a token stream into speakable sentences
# --------------------------------------------------------------------

_BOUNDARY = re.compile(r"""([.!?]+)(["')\]]*)(\s+)""")
_CLAUSE = re.compile(r"[,;:]\s")

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs",
    "e.g", "i.e", "inc", "ltd", "approx",
}


class SentenceChunker:
    """
    Accumulates streamed text (e.g. LLM tokens) and releases complete
    sentences as soon as they are known, so speech can start while the rest
    of the reply is still being generated.

        chunker = SentenceChunker()
        for piece in stream:
            for sentence in chunker.feed(piece):
                speak(sentence)
        for sentence in chunker.finish():
            speak(sentence)

    The first sentence may be released early at a comma once it is long
    enough, which shaves the time to first audio.
    """

    EAGER_MIN = 28       # characters before the first sentence may split at a comma
    MAX_CHARS = 220      # run-on sentences are cut here

    def __init__(self, eager_first: bool = True):

        self.eager_first = eager_first
        self._buffer = ""
        self.emitted = 0

    # ----------------------------------------------------------

    def feed(self, piece: str) -> list[str]:

        self._buffer += piece or ""

        out = []

        while True:

            sentence = self._next_sentence()

            if sentence is None:
                break

            cleaned = clean_for_speech(sentence)

            if cleaned:
                self.emitted += 1
                out.append(cleaned)

        return out

    def finish(self, truncated: bool = False) -> list[str]:
        """
        Flush what is left. If the model was cut off by its token limit
        (`truncated`), drop a dangling half-sentence rather than speaking it.
        """

        rest, self._buffer = self._buffer.strip(), ""

        if not rest:
            return []

        if truncated and self.emitted and rest[-1] not in ".!?\"')":
            return []

        cleaned = clean_for_speech(rest)

        if not cleaned:
            return []

        self.emitted += 1

        return [cleaned]

    # ----------------------------------------------------------

    def _next_sentence(self) -> str | None:

        buffer = self._buffer

        position = 0

        while True:

            match = _BOUNDARY.search(buffer, position)

            if not match:
                break

            if self._is_real_boundary(buffer[: match.start(1)], match.group(1)):

                sentence = buffer[: match.end(2)]
                self._buffer = buffer[match.end():]

                return sentence

            position = match.end()

        if self.eager_first and self.emitted == 0:

            for clause in _CLAUSE.finditer(buffer):

                if clause.start() + 1 >= self.EAGER_MIN:

                    sentence = buffer[: clause.start() + 1]
                    self._buffer = buffer[clause.end():]

                    return sentence

        if len(buffer) > self.MAX_CHARS:

            cut = buffer.rfind(" ", 0, self.MAX_CHARS)

            if cut <= 0:
                cut = self.MAX_CHARS

            self._buffer = buffer[cut:].lstrip()

            return buffer[:cut]

        return None

    @staticmethod
    def _is_real_boundary(before: str, punctuation: str) -> bool:
        """False for "Dr.", "e.g.", "J.", and list numbers like "3."."""

        if not punctuation.startswith("."):
            return True

        match = re.search(r"([A-Za-z.]+|\d+)$", before)

        if not match:
            return True

        word = match.group(1)
        lowered = word.lower().rstrip(".")

        if lowered in _ABBREVIATIONS:
            return False

        if len(word) == 1 and word.isalpha() and word.isupper():
            return False       # initials: "J. Smith"

        if word.isdigit() and len(punctuation) == 1:
            # "3. Next" is a list marker; "in 2024. Then" is a sentence end.
            return len(word) >= 4

        return True
