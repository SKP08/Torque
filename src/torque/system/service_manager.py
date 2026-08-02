from loguru import logger


class ServiceManager:
    """
    Initializes and manages all Torque services.
    """

    def __init__(self):
        self._services = []

    def register(self, service):
        self._services.append(service)

    def initialize(self):
        logger.info("Starting Service Manager...")

        for service in self._services:
            logger.info(f"Initializing {service.name}...")
            service.initialize()

        logger.success("All services initialized.")