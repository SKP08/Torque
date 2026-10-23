import json
import threading

from loguru import logger

from torque.paths import APPS_CACHE
from torque.system.app_scanner import AppScanner


class AppRegistry:
    """
    The list of installed apps. Scanning (PowerShell + Start Menu) takes
    seconds, so the last result is cached on disk: start-up uses the cache
    immediately and refreshes it in the background.
    """

    def __init__(self, scanner=None, cache_path=APPS_CACHE):

        self.scanner = scanner or AppScanner()
        self.cache_path = cache_path
        self.apps = []

    def load(self):

        cached = self._read_cache()

        if cached:

            self.apps = cached

            logger.success(f"Loaded {len(cached)} applications (cached).")

            threading.Thread(
                target=self.refresh,
                name="TorqueAppScan",
                daemon=True,
            ).start()

            return

        self.refresh()

    def refresh(self):

        logger.info("Scanning installed applications...")

        apps = self.scanner.scan()

        self.apps = apps       # replaced in one step, so readers never see a half-built list

        self._write_cache(apps)

        logger.success(f"Found {len(apps)} applications.")

    def _read_cache(self):

        if not self.cache_path:
            return None

        try:
            with open(self.cache_path, "r", encoding="utf-8") as file:
                apps = json.load(file)

            if isinstance(apps, list) and all(isinstance(a, dict) and "name" in a for a in apps):
                return apps

        except (OSError, ValueError):
            pass

        return None

    def _write_cache(self, apps):

        if not self.cache_path or not apps:
            return

        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)

            temporary = self.cache_path.with_suffix(".tmp")

            with open(temporary, "w", encoding="utf-8") as file:
                json.dump(apps, file)

            temporary.replace(self.cache_path)

        except OSError:
            logger.debug("Could not write the app cache.", exc_info=True)

    def all(self) -> list[dict]:

        return self.apps

    def find(self, name: str):

        name = name.lower().strip()

        for app in self.apps:

            if app["name"].lower() == name:
                return app

        return None
