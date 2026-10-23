import sys

from loguru import logger

from torque.paths import LOGS_DIR
from torque.system.service import Service


class LoggingService(Service):

    @property
    def name(self):
        return "Logging Service"

    def initialize(self):

        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        logger.remove()

        logger.add(
            LOGS_DIR / "torque.log",
            rotation="10 MB",
            retention=10,
            level="INFO",
            diagnose=False,
        )

        logger.add(
            sys.stderr,
            level="INFO",
            diagnose=False,
        )

        logger.info("Logging initialized.")
