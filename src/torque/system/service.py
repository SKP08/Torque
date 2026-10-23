from abc import ABC, abstractmethod


class Service(ABC):
    """
    Base class for every Torque service.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def initialize(self):
        pass

    def shutdown(self):
        """Release resources. Optional."""
