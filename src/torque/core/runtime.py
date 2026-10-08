import time

from loguru import logger

from torque.core.assistant_controller import AssistantController
from torque.system.bootstrap import Bootstrap
from torque.system.hotkey_service import HotkeyService
from torque.ui.ui_launcher import UILauncher


class TorqueRuntime:

    def __init__(self):
        self.bootstrap = Bootstrap()
        self.ui = UILauncher()
        self.controller = None

    def start(self):

        logger.info("Starting Torque Runtime...")

        # Initialize all services
        self.bootstrap.initialize()

        # Launch React UI
        self.ui.start()

        # Create Assistant Controller
        self.controller = AssistantController(
            self.bootstrap.manager
        )

        # Give HotkeyService access to the controller
        hotkey = self.bootstrap.manager.get(HotkeyService)

        if hotkey:
            hotkey.set_controller(self.controller)

        logger.success("Torque is running.")
        logger.info("Waiting for React UI to connect...")

        try:
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Torque shutting down...")