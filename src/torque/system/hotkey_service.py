import threading

import keyboard
from loguru import logger

from torque.system.service import Service


class HotkeyService(Service):

    def __init__(self):
        self.controller = None

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

    def set_controller(self, controller):
        self.controller = controller

    def _on_hotkey(self):
        logger.success("Global hotkey pressed.")

        if self.controller:
            threading.Thread(
                target=self.controller.activate,
                daemon=True,
            ).start()