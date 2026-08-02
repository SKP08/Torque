import keyboard
from loguru import logger

from torque.system.service import Service


class HotkeyService(Service):
    @property
    def name(self):
        return "Hotkey Service"

    def initialize(self):
        keyboard.add_hotkey(
            "ctrl+space",
            self._on_hotkey,
            suppress=False,
        )

        logger.info("Global hotkey registered: Ctrl+Space")

    def _on_hotkey(self):
        logger.success("Global hotkey pressed.")