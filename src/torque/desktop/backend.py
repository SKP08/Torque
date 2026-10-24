"""Mouse and keyboard on Windows (ctypes only). Everything else is injected in tests."""

import ctypes
import sys
import time

ALLOWED_KEYS = {
    "enter": 0x0D, "escape": 0x1B, "tab": 0x09, "space": 0x20, "backspace": 0x08,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "page up": 0x21, "page down": 0x22, "home": 0x24, "end": 0x23,
}

MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
INPUT_KEYBOARD = 1
MAX_TYPED = 300


def make_dpi_aware():
    """Without this, screenshot pixels and click pixels disagree on scaled displays."""

    if sys.platform != "win32":
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


class WindowsDesktop:

    def __init__(self):
        if sys.platform != "win32":
            raise NotImplementedError("desktop control")

        make_dpi_aware()

    def click(self, x: int, y: int, button: str = "left", double: bool = False):
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        time.sleep(0.05)

        down, up = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if button == "right" \
            else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)

        for _ in range(2 if double else 1):
            user32.mouse_event(down, 0, 0, 0, 0)
            user32.mouse_event(up, 0, 0, 0, 0)
            time.sleep(0.05)

    def scroll(self, amount: int):
        """Positive scrolls up, negative down (one notch = 120)."""

        ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(amount) * 120, 0)

    def press(self, key: str):
        code = ALLOWED_KEYS.get(key)

        if code is None:
            raise ValueError(f"key not allowed: {key}")

        user32 = ctypes.windll.user32
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, KEYEVENTF_KEYUP, 0)

    def type_text(self, text: str):
        """Types real characters (any language) with Unicode key events."""

        user32 = ctypes.windll.user32

        for char in text[:MAX_TYPED]:
            for flags in (KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP):
                _send_unicode(user32, ord(char), flags)

            time.sleep(0.01)


def _send_unicode(user32, code, flags):
    class KeyboardInput(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                    ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class InputUnion(ctypes.Union):
        _fields_ = [("ki", KeyboardInput), ("pad", ctypes.c_byte * 32)]

    class Input(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", InputUnion)]

    item = Input(INPUT_KEYBOARD, InputUnion(ki=KeyboardInput(0, code, flags, 0, None)))
    user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))
