import sys
import time

from loguru import logger

from torque.paths import ensure_dirs
from torque.system.bootstrap import Bootstrap
from torque.system.config_service import load_config
from torque.system.hotkey_service import HotkeyService
from torque.ui.ui_launcher import UILauncher
from torque.websocket.websocket_service import WebSocketService


class TorqueRuntime:

    def __init__(self):
        self.bootstrap = Bootstrap()
        self.ui = UILauncher()
        self.controller = None

    def start(self):

        ensure_dirs()

        try:
            self._start()
        finally:
            self.shutdown()

    def _start(self):

        logger.info("Starting Torque Runtime...")

        # Config, logging, database, websocket, hotkey.
        self.bootstrap.initialize()

        config = load_config()
        manager = self.bootstrap.manager
        ws = manager.get(WebSocketService)

        if ws:
            ws.send({"state": "loading", "message": "Loading..."})

        self.ui.start()

        # Heavy: loads Whisper, Piper and the LLM at the same time.
        try:
            from torque.core.assistant_controller import AssistantController

            self.controller = AssistantController(manager)

        except Exception as error:  # noqa: BLE001
            logger.exception("Torque could not finish starting.")

            if ws:
                ws.send({"state": "error", "message": str(error)[:120]})
                time.sleep(0.5)

            sys.exit(1)

        hotkey = manager.get(HotkeyService)

        if hotkey:
            hotkey.set_controller(self.controller)

        self.controller.start()

        how = f"Press {config['hotkey']}"

        if config["wake_word_enabled"]:
            how = f"Say 'Hey Torque' or press {config['hotkey']}"

        logger.success(f"Torque is running. {how} to talk.")

        self._run_foreground(config)

    def _run_foreground(self, config):
        """
        Keep the main thread alive. With a tray icon the tray owns the main
        thread (required on Windows); otherwise just wait for Ctrl+C.
        """

        if config["tray_enabled"]:

            try:
                from torque.ui.tray import TorqueTray

                tray = TorqueTray(
                    on_talk=self.controller.toggle,
                    on_open=self.ui.open_window,
                )
                tray.run()
                return

            except Exception:  # noqa: BLE001
                logger.warning("System tray unavailable; running without it.")

        try:
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            logger.info("Torque shutting down...")

    def shutdown(self):

        logger.info("Shutting down Torque...")

        if self.controller:
            self.controller.shutdown()

        self.ui.stop()

        self.bootstrap.shutdown()
