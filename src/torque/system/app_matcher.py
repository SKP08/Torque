import re

from rapidfuzz import fuzz

from torque.system.app_registry import AppRegistry


def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", text).strip()


class AppMatcher:
    """
    Resolves a spoken app name to an installed application.

    Matching is deliberately strict: a wrong app launching is worse than
    "I couldn't find that". Short or vague queries never match.
    """

    ALIASES = {
        # Browsers
        "chrome": "google chrome",
        "browser": "google chrome",
        "edge": "microsoft edge",
        "firefox": "firefox",

        # VS Code
        "code": "visual studio code",
        "vscode": "visual studio code",
        "vs code": "visual studio code",

        # Explorer
        "explorer": "file explorer",
        "files": "file explorer",
        "file manager": "file explorer",
        "windows explorer": "file explorer",

        # Terminal
        "cmd": "command prompt",
        "terminal": "windows terminal",
        "powershell": "windows powershell",
        "power shell": "windows powershell",

        # Utilities
        "calc": "calculator",
        "task manager": "task manager",
        "settings": "settings",
        "snipping tool": "snipping tool",

        # Common apps
        "word": "word",
        "excel": "excel",
        "powerpoint": "powerpoint",
        "teams": "microsoft teams",
        "whatsapp": "whatsapp",
    }

    MIN_QUERY_LENGTH = 3
    FUZZY_THRESHOLD = 85

    def __init__(self, registry=None):

        self.registry = registry or AppRegistry()

    def load(self):

        self.registry.load()

    @staticmethod
    def _shortest(candidates):
        # Prefer the simplest name ("Chrome" over "Chrome Remote Desktop").
        return min(candidates, key=lambda c: (len(c[1]), c[1]))[0]

    def match(self, query: str):

        query = _norm(query)

        query = (
            self.ALIASES.get(query)
            or self.ALIASES.get(query.replace(" ", ""))
            or query
        )

        compact = query.replace(" ", "")

        if len(compact) < self.MIN_QUERY_LENGTH:
            return None

        entries = [(app, _norm(app["name"])) for app in self.registry.all()]

        tokens = query.split()

        # 1. Exact name.
        exact = [e for e in entries if e[1] == query]

        if exact:
            return exact[0][0]

        # 2. Query is the start of the name ("visual studio" -> Visual Studio Code).
        prefix = [e for e in entries if e[1].split()[: len(tokens)] == tokens]

        if prefix:
            return self._shortest(prefix)

        # 3. Every query word appears as a whole word in the name.
        contained = [e for e in entries if set(tokens) <= set(e[1].split())]

        if contained:
            return self._shortest(contained)

        # 4. Same letters ignoring spaces ("power shell" / "powershell").
        squashed = [e for e in entries if e[1].replace(" ", "") == compact]

        if squashed:
            return self._shortest(squashed)

        # 5. Single word that begins a name word ("disc" -> Discord).
        if len(tokens) == 1 and len(query) >= 4:

            begins = [
                e for e in entries
                if any(word.startswith(query) for word in e[1].split())
            ]

            if begins:
                return self._shortest(begins)

        # 6. Fuzzy, to tolerate speech-recognition slips ("spotifi").
        if len(compact) >= 4:

            best = None
            best_score = 0

            for app, name in entries:

                score = fuzz.token_sort_ratio(query, name)

                if score > best_score:
                    best, best_score = app, score

            if best_score >= self.FUZZY_THRESHOLD:
                return best

        return None
