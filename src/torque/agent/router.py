import re

_ACTION = re.compile(
    r"\b(?:unzip|un-zip|extract|copy|move|find|locate|search for|where(?:'s| is)|"
    r"make (?:a |me a )?(?:new )?folder|create (?:a )?(?:new )?folder|"
    r"list (?:the )?(?:files|contents)|what(?:'s| is) in)\b"
)

_OBJECT = re.compile(
    r"\b(?:files?|folders?|zip|zipped|archive|downloads?|documents?|directory|"
    r"drive|disk|desktop|pdfs?|hard ?disk)\b"
)

# Questions about how to do it in code are chat, not tasks.
_NOT_A_TASK = re.compile(
    r"^(?:how|why|explain|what(?:'s| is) the (?:difference|best)|can you explain|tell me how)\b"
    r"|\b(?:python|javascript|java|linux|bash|powershell|command|git|script|code|function|api)\b"
)


def wants_agent(text: str) -> bool:
    """True for file tasks like "unzip my latest download into D:\\Projects"."""

    said = re.sub(r"[.!?,]", " ", (text or "").lower())
    said = re.sub(r"\s+", " ", said).strip()

    if _NOT_A_TASK.search(said):
        return False

    return bool(_ACTION.search(said) and _OBJECT.search(said))


_BROWSE = re.compile(
    r"\b(?:browse|browser)\b"
    r"|\b(?:go|navigate|head) to [\w.-]+\.(?:com|org|net|io|ca|in|edu|gov|co|dev|app|ai|uk)\b"
    r"|\bvisit [\w.-]+\.(?:com|org|net|io|ca|in|edu|gov|co|dev|app|ai|uk)\b"
    r"|\b(?:open|go to) (?:the )?(?:website|web ?site|web page|webpage)\b"
    r"|\b(?:search|look) (?:the web |online |google |the internet )?(?:and|then) (?:open|click|read|go)\b"
)


def wants_browser(text: str) -> bool:
    """True for web tasks the user spells out ("go to wikipedia.org and read the first paragraph")."""

    said = re.sub(r"[!?,]", " ", (text or "").lower())
    said = re.sub(r"\s+", " ", said).strip()

    if re.match(r"^(?:how|why|explain|what(?:'s| is) the (?:difference|best))\b", said):
        return False

    return bool(_BROWSE.search(said))
