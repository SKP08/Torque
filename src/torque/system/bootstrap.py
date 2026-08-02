from loguru import logger

from torque.system.database_service import DatabaseService
from torque.system.logging_service import LoggingService


class Bootstrap:
    """
    Initializes all Torque services.
    """

    def initialize(self):
        logger.info("Initializing services...")

        LoggingService().initialize()
        DatabaseService().initialize()

        logger.success("All services initialized.")