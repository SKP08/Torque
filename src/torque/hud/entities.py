"""
Which things should the panels show? Cheap, predictable heuristics, no LLM:
named things in the answer first ("New Delhi"), then in the question ("India").
Wikipedia then confirms each one actually exists.
"""

import re

# Questions worth illustrating. Personal and PC questions are handled elsewhere.
INFO_QUESTION = re.compile(
    r"^(?:what|who|where|when|which)(?:'s| is| are| was| were| did| does)\b"
    r"|^(?:tell me about|show me|explain|describe|give me (?:some )?info(?:rmation)? (?:on|about))\b"
    r"|\b(?:capital|president|prime minister|population|founder|inventor|tallest|largest|biggest|smallest|oldest) of\b"
    r"|^how (?:tall|big|old|far|long|deep|large|many people)\b"
    r"|^who (?:invented|discovered|wrote|painted|built|founded|directed)\b"
    r"|^where (?:is|are)\b"
)

NOT_INFO = re.compile(
    r"\b(?:my|i|i'm|your|you|weather|time|date|today|tomorrow|joke|volume|brightness|"
    r"cpu|ram|memory|network|port|screen|error|file|folder|download|timer|reminder)\b"
)

# Words that are capitalised only because they start a sentence.
SKIP = {
    "the", "a", "an", "it", "its", "it's", "this", "that", "these", "those", "there", "here", "he", "she",
    "they", "we", "you", "i", "my", "your", "his", "her", "their", "our", "and", "but", "or", "so", "yes",
    "no", "sure", "okay", "ok", "well", "however", "also", "in", "on", "at", "of", "as", "by", "for",
    "from", "with", "about", "today", "currently", "according", "torque", "sorry", "unfortunately",
    "based", "while", "since", "when", "after", "before", "because", "although", "if", "one", "some",
    "many", "most", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
    "november", "december", "right", "away", "done", "let", "what", "who", "where", "when", "which",
    "how", "why", "tell", "show", "explain", "describe", "give",
}

CONNECTORS = {"of", "the", "de", "la", "del", "von", "van", "du", "al", "el", "bin", "da", "di"}

_WORD = re.compile(r"[A-Za-z][A-Za-z.'\u2019-]*")


def is_info_question(text: str) -> bool:

    said = " ".join((text or "").lower().replace("?", " ").replace(",", " ").split())

    if not said or not INFO_QUESTION.search(said):
        return False

    return not NOT_INFO.search(said)


def capitalised_phrases(text: str) -> list[str]:
    """'New Delhi', 'Taj Mahal', 'Republic of India': runs of Capitalised Words."""

    words = [(m.group(), m.start()) for m in _WORD.finditer(text)]

    phrases, current = [], []

    def flush():
        nonlocal current

        while current and current[-1].lower() in CONNECTORS:
            current.pop()

        if current and not (len(current) == 1 and current[0].lower().strip(".'") in SKIP):
            phrases.append(" ".join(current).strip(".'"))

        current = []

    previous_end = None

    for word, start in words:

        # A comma, dash or any punctuation between words ends the phrase:
        # "Paris, France" is two things, not "Paris France".
        if previous_end is not None and text[previous_end:start].strip(" "):
            flush()

        previous_end = start + len(word)

        bare = word.strip(".'\u2019")

        if bare[:1].isupper() and not (bare.lower() in SKIP and not current and len(bare) < 4):
            current.append(bare)

        elif current and bare.lower() in CONNECTORS:
            current.append(bare.lower())

        else:
            flush()

    flush()

    return phrases


QUESTION_SUBJECT = re.compile(
    r"(?:capital|president|prime minister|population|founder|currency|language|flag|leader|"
    r"tallest|largest|biggest|smallest|oldest|highest|longest) of (?:the )?([a-z][a-z .'-]+?)(?:\s*\?|$| and\b)"
    r"|(?:tell me about|show me|explain|describe|who (?:is|was|are|were)|what (?:is|are|was|were)|where (?:is|are)) "
    r"(?:the |a |an )?([a-z][a-z .'-]+?)(?:\s*\?|$| on\b| and\b)",
)


def title_case(text: str) -> str:

    return " ".join(w if w in CONNECTORS else w.capitalize() for w in text.split())


def extract_entities(question: str, answer: str, limit: int = 3) -> list[str]:
    """Candidates in priority order: the answer's things, then the question's."""

    found, seen = [], set()

    def add(name):

        key = name.lower()

        if name and key not in seen and key not in SKIP and len(name) > 2:
            seen.add(key)
            found.append(name)

    for phrase in capitalised_phrases(answer):
        add(phrase)

    for phrase in capitalised_phrases(question):
        add(phrase)

    match = QUESTION_SUBJECT.search((question or "").lower())

    if match:
        subject = next(g for g in match.groups() if g)

        if subject.strip() not in ("it", "this", "that", "he", "she", "they"):
            add(title_case(subject.strip()))

    return found[: limit + 3]            # a few spares: some won't resolve on Wikipedia
