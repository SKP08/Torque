"""A tiny hook so any part of Torque can tell the user something (toast + speech) without
knowing about the controller. The controller registers itself on start."""

_handler = None


def set_announcer(handler):
    global _handler
    _handler = handler


def announce(message: str, severity: str = "info", speak: bool = True) -> bool:
    """True if someone was there to receive it."""

    if _handler is None:
        return False

    _handler(message, severity, speak)

    return True
