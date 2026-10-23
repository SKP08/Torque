import threading

import keyboard
from loguru import logger

from torque.system.config_service import load_config
from torque.system.service import Service


class HotkeyService(Service):
    """
    Global hotkey. Pressing it starts a conversation; pressing it again
    while a conversation is active cancels it.
    """

    def __init__(self):
        self.controller = None
        self.hotkey = None

    @property
    def name(self):
        return "Hotkey Service"

    def initialize(self):

        config = load_config()

        self.hotkey = config["hotkey"]

        try:
            keyboard.add_hotkey(
                self.hotkey,
                self._on_hotkey,
                suppress=bool(config["hotkey_suppress"]),
            )

            logger.info(f"Global hotkey registered: {self.hotkey}")

        except Exception:  # noqa: BLE001
            # Torque is still usable (tray / UI text input) without it.
            logger.exception(f"Could not register hotkey '{self.hotkey}'.")

    def shutdown(self):

        try:
            keyboard.unhook_all_hotkeys()
        except Exception:  # noqa: BLE001
            logger.debug("Hotkey cleanup failed.", exc_info=True)

    def set_controller(self, controller):
        self.controller = controller

    def _on_hotkey(self):

        logger.info("Global hotkey pressed.")

        if self.controller:
            threading.Thread(
                target=self.controller.toggle,
                name="TorqueToggle",
                daemon=True,
            ).start()
