import threading
import time

from loguru import logger

from torque.system.bootstrap import Bootstrap
from torque.ui.tray import TorqueTray


class TorqueRuntime:

    def __init__(self):

        self.bootstrap = Bootstrap()
        self.tray = TorqueTray()

    def start(self):

        logger.info("Starting Torque Runtime...")

        self.bootstrap.initialize()

        logger.success("Torque is running.")

        tray_thread = threading.Thread(
            target=self.tray.run,
            daemon=True,
        )

        tray_thread.start()

        try:

            while True:
                time.sleep(0.1)

        except KeyboardInterrupt:

            logger.info("Torque shutting down...")

            self.tray.stop()