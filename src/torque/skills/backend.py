import ctypes
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

VK = {
    "mute": 0xAD, "down": 0xAE, "up": 0xAF,
    "next": 0xB0, "previous": 0xB1, "play_pause": 0xB3,
    "win": 0x5B, "d": 0x44, "alt": 0x12, "tab": 0x09,
}

KEYUP = 0x0002


class UnsupportedBackend:
    """Used off Windows: every operation says so."""

    def __getattr__(self, name):

        def unsupported(*args, **kwargs):
            raise NotImplementedError(name)

        return unsupported


class WindowsBackend:
    """The Windows calls behind each skill. Nothing else touches ctypes."""

    # ---- keyboard ------------------------------------------------

    @staticmethod
    def _key(*names, pause=0.0):

        user32 = ctypes.windll.user32

        for name in names:
            user32.keybd_event(VK[name], 0, 0, 0)

        for name in reversed(names):
            user32.keybd_event(VK[name], 0, KEYUP, 0)

        if pause:
            time.sleep(pause)

    def media(self, key: str):
        self._key(key)

    def volume_step(self, direction: str, times: int = 1):

        for _ in range(times):
            self._key(direction, pause=0.004)

    def set_volume(self, percent: int):
        """Each key press is 2%: drop to zero, then climb to the target."""

        self.volume_step("down", 50)
        self.volume_step("up", round(percent / 2))

    def show_desktop(self):
        self._key("win", "d")

    def switch_window(self):
        self._key("alt", "tab")

    # ---- system --------------------------------------------------

    def lock(self):
        ctypes.windll.user32.LockWorkStation()

    def screenshot(self) -> Path:

        from PIL import ImageGrab

        folder = Path.home() / "Pictures" / "Torque"
        folder.mkdir(parents=True, exist_ok=True)

        path = folder / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"

        ImageGrab.grab(all_screens=True).save(path)

        return path

    def shutdown(self):
        subprocess.run(["shutdown", "/s", "/t", "5"], check=True)

    def restart(self):
        subprocess.run(["shutdown", "/r", "/t", "5"], check=True)

    def sleep(self):
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True
        )

    # ---- display -------------------------------------------------

    @staticmethod
    def _powershell(script: str) -> str:

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )

        return result.stdout.strip()

    def get_brightness(self) -> int:

        return int(self._powershell(
            "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness)"
            ".CurrentBrightness | Select-Object -First 1"
        ))

    def set_brightness(self, percent: int):

        percent = max(0, min(100, int(percent)))

        self._powershell(
            "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1, {percent})"
        )


def default_backend():

    return WindowsBackend() if sys.platform == "win32" else UnsupportedBackend()
