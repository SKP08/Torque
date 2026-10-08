from torque.system.config_service import ConfigService
from torque.system.database_service import DatabaseService
from torque.system.hotkey_service import HotkeyService
from torque.system.logging_service import LoggingService

from torque.websocket.websocket_service import WebSocketService


def get_services():
    """
    Returns every Torque service that should be started.
    """

    return [
        ConfigService(),
        LoggingService(),
        DatabaseService(),
        HotkeyService(),
        WebSocketService(),
    ]