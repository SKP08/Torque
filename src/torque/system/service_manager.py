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

            try:
                service.initialize()
            except Exception:
                logger.exception(f"{service.name} failed to initialize.")
                raise

        logger.success("All services initialized.")

    def shutdown(self):
        """
        Stop services in reverse order. One failing service never blocks
        the others from shutting down.
        """

        for service in reversed(self._services):
            try:
                service.shutdown()
            except Exception:
                logger.exception(f"{service.name} failed to shut down.")

    def get(self, service_type):
        """
        Return the first service matching the given class.
        """

        for service in self._services:
            if isinstance(service, service_type):
                return service

        return None
