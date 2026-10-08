from torque.system.service_manager import ServiceManager
from torque.system.service_registry import get_services


class Bootstrap:

    def __init__(self):
        self.manager = ServiceManager()

    def initialize(self):
        for service in get_services():
            self.manager.register(service)

        self.manager.initialize()