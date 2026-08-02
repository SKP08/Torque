from torque.system.service_manager import ServiceManager
from torque.system.service_registry import get_services


class Bootstrap:

    def initialize(self):

        manager = ServiceManager()

        for service in get_services():
            manager.register(service)

        manager.initialize()