import json
import subprocess
import sys
from pathlib import Path

from loguru import logger


def parse_start_apps(output: str) -> list[dict]:
    """
    Parse the JSON produced by `Get-StartApps | ConvertTo-Json`.
    Returns [{"name": ..., "appid": ...}].
    """

    try:
        data = json.loads(output)
    except (TypeError, ValueError):
        return []

    if isinstance(data, dict):
        data = [data]

    apps = []

    for item in data if isinstance(data, list) else []:

        name = str(item.get("Name") or "").strip()
        appid = str(item.get("AppID") or "").strip()

        if name and appid:
            apps.append({"name": name, "appid": appid})

    return apps


class AppScanner:
    """
    Finds launchable apps: Start Menu shortcuts first, then everything
    else Windows lists (Microsoft Store/UWP apps such as Calculator and
    Settings) via Get-StartApps.
    """

    START_MENU_PATHS = (
        Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
        Path.home() / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
    )

    def _scan_shortcuts(self) -> list[dict]:

        apps = []

        for root in self.START_MENU_PATHS:

            if not root.exists():
                continue

            for shortcut in root.rglob("*.lnk"):

                name = shortcut.stem.strip()

                if name:
                    apps.append({"name": name, "shortcut": str(shortcut)})

        return apps

    def _scan_start_apps(self) -> list[dict]:

        if sys.platform != "win32":
            return []

        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-StartApps | ConvertTo-Json -Compress",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            return parse_start_apps(result.stdout)

        except Exception:  # noqa: BLE001
            logger.warning("Get-StartApps failed; using Start Menu shortcuts only.")
            return []

    def scan(self) -> list[dict]:

        apps = []
        seen = set()

        for app in self._scan_shortcuts() + self._scan_start_apps():

            key = app["name"].lower()

            if key in seen:
                continue

            seen.add(key)
            apps.append(app)

        apps.sort(key=lambda app: app["name"].lower())

        return apps
