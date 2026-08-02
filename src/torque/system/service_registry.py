from torque.system.config_service import ConfigService
from torque.system.database_service import DatabaseService
from torque.system.logging_service import LoggingService


def get_services():
    """
    Returns every Torque service that should be started.
    """

    return [
        ConfigService(),
        LoggingService(),
        DatabaseService(),
    ]