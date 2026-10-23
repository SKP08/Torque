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
