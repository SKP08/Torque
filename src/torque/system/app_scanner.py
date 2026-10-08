from pathlib import Path


class AppScanner:

    START_MENU_PATHS = (
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
        Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
    )

    def scan(self) -> list[dict]:

        apps = []
        seen = set()

        for root in self.START_MENU_PATHS:

            if not root.exists():
                continue

            for shortcut in root.rglob("*.lnk"):

                name = shortcut.stem.strip()

                if not name:
                    continue

                key = name.lower()

                if key in seen:
                    continue

                seen.add(key)

                apps.append(
                    {
                        "name": name,
                        "shortcut": str(shortcut),
                    }
                )

        apps.sort(
            key=lambda app: app["name"].lower()
        )

        return apps