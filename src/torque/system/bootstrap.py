from torque.system.database_service import DatabaseService
from torque.system.logging_service import LoggingService
from torque.system.service_manager import ServiceManager


class Bootstrap:

    def initialize(self):

        manager = ServiceManager()

        manager.register(LoggingService())
        manager.register(DatabaseService())

        manager.initialize()