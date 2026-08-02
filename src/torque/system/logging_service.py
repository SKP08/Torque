from pathlib import Path

from loguru import logger

from torque.system.service import Service


class LoggingService(Service):

    @property
    def name(self):
        return "Logging Service"

    def initialize(self):

        Path("logs").mkdir(exist_ok=True)

        logger.remove()

        logger.add(
            "logs/torque.log",
            rotation="10 MB",
            retention=10,
            level="INFO",
        )

        logger.add(
            lambda msg: print(msg, end=""),
            level="INFO",
        )

        logger.info("Logging initialized.")