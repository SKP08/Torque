import re

_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_MARKS = re.compile(r"[*_`#>]+")
_BULLET = re.compile(r"^\s*(?:[-•*]|\d+[.)])\s+", re.MULTILINE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:

    text = re.sub(r"\s+", " ", text or "").strip()

    if not text:
        return []

    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def to_speech(text: str, max_sentences: int = 4, max_chars: int = 500) -> str:
    """
    Turn text that was written to be read (markdown, links, bullets) into
    something short and natural to speak aloud.
    """

    if not text:
        return ""

    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("", text)
    text = _BULLET.sub("", text)
    text = _MD_MARKS.sub("", text)
    text = text.replace("\n", ". ")
    text = re.sub(r"\.\s*\.", ".", text)

    sentences = split_sentences(text)

    spoken = []
    length = 0

    for sentence in sentences[:max_sentences]:

        if spoken and length + len(sentence) > max_chars:
            break

        spoken.append(sentence)
        length += len(sentence) + 1

    return " ".join(spoken).strip()
