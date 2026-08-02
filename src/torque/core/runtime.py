import time

from loguru import logger

from torque.system.bootstrap import Bootstrap


class TorqueRuntime:
    """
    Main runtime of Torque.
    Responsible for starting every subsystem.
    """

    def __init__(self):
        self.bootstrap = Bootstrap()

    def start(self):
        logger.info("Starting Torque Runtime...")

        self.bootstrap.initialize()

        logger.success("Torque is running.")

        try:
            while True:
                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("Torque shutting down...")