from loguru import logger


class ServiceManager:
    """
    Initializes and manages all Torque services.
    """

    def __init__(self):
        self._services = []

    @property
    def services(self):
        return self._services

    def register(self, service):
        self._services.append(service)

    def initialize(self):
        logger.info("Starting Service Manager...")

        for service in self._services:
            logger.info(f"Initializing {service.name}...")
            service.initialize()

        logger.success("All services initialized.")

    def get(self, service_type):
        """
        Return the first service matching the given class.
        """

        for service in self._services:
            if isinstance(service, service_type):
                return service

        return None