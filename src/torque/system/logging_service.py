from pathlib import Path

from loguru import logger


class LoggingService:

    def initialize(self):

        log_path = Path("logs")

        log_path.mkdir(exist_ok=True)

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