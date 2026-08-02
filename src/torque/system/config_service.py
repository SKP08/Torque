import json
from pathlib import Path

from loguru import logger

from torque.system.service import Service

DEFAULT_CONFIG = {
    "assistant_name": "Torque",
    "startup": True,
    "hotkey": "ctrl+space",
    "theme": "dark",
    "voice_enabled": True,
    "notifications": True,
}


class ConfigService(Service):
    """
    Loads and manages Torque configuration.
    """

    CONFIG_PATH = Path("config/settings.json")

    @property
    def name(self) -> str:
        return "Configuration Service"

    def initialize(self):

        self.CONFIG_PATH.parent.mkdir(exist_ok=True)

        if not self.CONFIG_PATH.exists():

            with open(self.CONFIG_PATH, "w", encoding="utf-8") as file:
                json.dump(DEFAULT_CONFIG, file, indent=4)

            logger.info("Created default configuration.")

        else:
            logger.info("Configuration loaded.")

    def load(self):

        with open(self.CONFIG_PATH, "r", encoding="utf-8") as file:
            return json.load(file)