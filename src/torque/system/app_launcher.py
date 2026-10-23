import os
import subprocess
import sys

from loguru import logger

from torque.system.app_matcher import AppMatcher
from torque.system.system_commands import ActionResult

# Closing these would take down the desktop or the OS.
PROTECTED_PROCESSES = {
    "explorer.exe", "csrss.exe", "winlogon.exe", "wininit.exe", "services.exe",
    "lsass.exe", "svchost.exe", "smss.exe", "dwm.exe", "system", "registry",
    "fontdrvhost.exe",
}

KNOWN_PROCESSES = {
    "google chrome": "chrome.exe",
    "microsoft edge": "msedge.exe",
    "firefox": "firefox.exe",
    "brave": "brave.exe",
    "discord": "Discord.exe",
    "notepad": "notepad.exe",
    "visual studio code": "Code.exe",
    "spotify": "Spotify.exe",
    "steam": "steam.exe",
    "calculator": "CalculatorApp.exe",
}


class AppLauncher:

    def __init__(self, matcher=None):

        self.matcher = matcher or AppMatcher()

        if matcher is None:
            self.matcher.load()

    # ==========================================================
    # OPEN
    # ==========================================================

    def launch(self, query: str) -> ActionResult:

        app = self.matcher.match(query)

        if not app:
            logger.warning(f"Application not found: {query}")

            return ActionResult(False, f"I couldn't find {query} on your computer.")

        try:
            logger.info(f"Launching {app['name']}")

            if app.get("shortcut"):
                os.startfile(app["shortcut"])
            else:
                subprocess.Popen(
                    ["explorer.exe", f"shell:AppsFolder\\{app['appid']}"]
                )

            return ActionResult(True, f"Opening {app['name']}.")

        except Exception:  # noqa: BLE001
            logger.exception(f"Could not launch {app['name']}")

            return ActionResult(False, f"I couldn't open {app['name']}.")

    # ==========================================================
    # CLOSE
    # ==========================================================

    def close(self, query: str) -> ActionResult:
        """
        Ask the app to close politely (like clicking X). Apps with unsaved
        work get to prompt instead of being killed.
        """

        app = self.matcher.match(query)

        if not app:
            return ActionResult(False, f"I couldn't find {query} on your computer.")

        name = app["name"]

        executables = self._find_executables(name)

        if not executables:
            return ActionResult(False, f"I couldn't tell which program {name} is running as.")

        blocked = [e for e in executables if e.lower() in PROTECTED_PROCESSES]

        if blocked:
            return ActionResult(
                False,
                f"I won't close {name}. It would take down your desktop.",
            )

        if sys.platform != "win32":
            return ActionResult(False, "Closing apps is only supported on Windows.")

        closed = False

        for executable in executables:

            result = subprocess.run(
                ["taskkill", "/IM", executable, "/T"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode == 0:
                closed = True

        if closed:
            return ActionResult(True, f"Closing {name}.")

        return ActionResult(False, f"{name} doesn't seem to be running.")

    # ==========================================================
    # PROCESS LOOKUP
    # ==========================================================

    def _find_executables(self, app_name: str) -> list[str]:

        key = app_name.lower().strip()

        known = KNOWN_PROCESSES.get(key)

        if known:
            return [known]

        if key in ("file explorer", "windows explorer"):
            return ["explorer.exe"]

        # Otherwise look for a running process named like the app.
        try:
            import psutil
        except ImportError:
            return []

        words = {w for w in key.replace("-", " ").split() if len(w) >= 4}
        squashed = key.replace(" ", "")

        found = set()

        for process in psutil.process_iter(["name"]):

            name = process.info.get("name") or ""
            stem = name.lower().removesuffix(".exe")

            if stem and (stem == squashed or stem in words):
                found.add(name)

        return sorted(found)
