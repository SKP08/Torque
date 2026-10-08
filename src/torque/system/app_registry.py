from loguru import logger

from torque.system.app_scanner import AppScanner


class AppRegistry:

    def __init__(self):

        self.scanner = AppScanner()
        self.apps = []

    def load(self):

        logger.info("Scanning installed applications...")

        self.apps = self.scanner.scan()

        logger.success(
            f"Loaded {len(self.apps)} applications."
        )

    def all(self) -> list[dict]:

        return self.apps

    def find(self, name: str):

        name = name.lower().strip()

        for app in self.apps:

            if app["name"].lower() == name:
                return app

        return None