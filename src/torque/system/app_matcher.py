from rapidfuzz import fuzz

from torque.system.app_registry import AppRegistry


class AppMatcher:

    ALIASES = {
        # Browsers
        "chrome": "google chrome",
        "browser": "google chrome",
        "edge": "microsoft edge",

        # VS Code
        "code": "visual studio code",
        "vscode": "visual studio code",
        "vs code": "visual studio code",

        # Explorer
        "explorer": "file explorer",
        "file explorer": "file explorer",
        "windows explorer": "file explorer",

        # Terminal
        "cmd": "command prompt",
        "command prompt": "command prompt",
        "terminal": "windows terminal",
        "powershell": "windows powershell",

        # Utilities
        "paint": "paint",
        "notepad": "notepad",
        "calculator": "calculator",
        "calc": "calculator",

        # Common apps
        "discord": "discord",
        "spotify": "spotify",
        "steam": "steam",
        "obs": "obs",
    }

    def __init__(self):

        self.registry = AppRegistry()

    def load(self):

        self.registry.load()

    def match(self, query: str):

        query = (
            query.lower()
            .strip()
            .rstrip(".,!?")
        )

        # Resolve aliases
        query = self.ALIASES.get(query, query)

        apps = self.registry.all()

        # ---------------- Exact ----------------

        for app in apps:

            if app["name"].lower() == query:
                return app

        # ---------------- Contains ----------------

        for app in apps:

            if query in app["name"].lower():
                return app

        # ---------------- Fuzzy ----------------

        best = None
        score = 0

        for app in apps:

            s = fuzz.token_sort_ratio(
                query,
                app["name"].lower(),
            )

            if s > score:

                score = s
                best = app

        if score >= 75:

            return best

        return None