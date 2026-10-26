"""
Phone alerts through ntfy (https://ntfy.sh): free, no account. Install the ntfy app, subscribe to
a long random topic name, and put the same name in config/settings.local.json (never committed):

    {"push_enabled": true, "push_topic": "torque-<random letters>"}

Anyone who knows the topic can read the alerts, so make it unguessable. Alert text may mention
program names, so don't use a short topic. Self-hosted servers work too (push_server).
Nothing is sent unless push_enabled is true and a topic is set. Only the short alert text is sent.
"""

import ctypes
import sys
import threading
import time
import urllib.request

from loguru import logger

PRIORITY = {"warn": "high", "info": "default"}


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input (0 where unknown, so we never push by mistake)."""

    if sys.platform != "win32":
        return 0.0

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

    info = LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(info)

    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0

    return max(0.0, (ctypes.windll.kernel32.GetTickCount() - info.dwTime) / 1000.0)


def _post(url, data, headers, timeout=8):
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status


class Pusher:
    """send() is non-blocking and never raises. Pushes only when you are away from the PC (min_idle seconds,
    0 = always), only for the chosen severities, and never repeats the same message within `repeat_after`."""

    def __init__(self, topic, server="https://ntfy.sh", min_idle=120.0, levels=("warn",), idle_fn=idle_seconds,
                 post=_post, clock=time.monotonic, repeat_after=600.0, background=True):
        self.topic = (topic or "").strip().strip("/")
        self.server = server.rstrip("/")
        self.min_idle = float(min_idle)
        self.levels = set(levels)
        self.idle_fn = idle_fn
        self.post = post
        self.clock = clock
        self.repeat_after = repeat_after
        self.background = background
        self._sent = {}

    @property
    def enabled(self):
        return bool(self.topic) and self.server.startswith("https://")

    def should_send(self, message, severity, force=False) -> bool:
        if not self.enabled:
            return False

        if not force:
            if severity not in self.levels:
                return False

            try:
                if self.min_idle and self.idle_fn() < self.min_idle:
                    return False
            except Exception:  # noqa: BLE001
                return False

        now = self.clock()

        if now - self._sent.get(message, -1e9) < self.repeat_after:
            return False

        self._sent[message] = now

        if len(self._sent) > 100:
            self._sent = {m: t for m, t in self._sent.items() if now - t < self.repeat_after}

        return True

    def send(self, message, severity="info", force=False) -> bool:
        """True if a push was started."""

        if not self.should_send(message, severity, force):
            return False

        def job():
            try:
                self.post(f"{self.server}/{self.topic}", message.encode("utf-8"),
                          {"Title": "Torque", "Priority": PRIORITY.get(severity, "default"), "Tags": "robot"})
            except Exception:  # noqa: BLE001
                logger.warning("Could not send the phone alert.")

        if self.background:
            threading.Thread(target=job, name="TorquePush", daemon=True).start()
        else:
            job()

        return True


def build_pusher(config):
    if not config.get("push_enabled") or not config.get("push_topic"):
        return None

    return Pusher(config["push_topic"], config.get("push_server", "https://ntfy.sh"),
                  min_idle=config.get("push_idle_seconds", 120), levels=config.get("push_levels", ["warn"]))
