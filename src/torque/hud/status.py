import time

import psutil


def _battery():

    try:
        battery = psutil.sensors_battery()
    except (AttributeError, OSError):
        return None

    if battery is None:
        return None

    return {"percent": round(battery.percent), "plugged": bool(battery.power_plugged)}


class NetworkRate:
    """Bytes per second since the previous call."""

    def __init__(self):

        self._last = None

    def read(self):

        counters = psutil.net_io_counters()
        now = time.monotonic()

        if self._last is None:
            self._last = (now, counters.bytes_recv, counters.bytes_sent)
            return 0.0, 0.0

        then, down, up = self._last
        elapsed = max(now - then, 0.001)

        self._last = (now, counters.bytes_recv, counters.bytes_sent)

        return (counters.bytes_recv - down) / elapsed, (counters.bytes_sent - up) / elapsed


def system_status(probe=None, rate=None, blocking=True) -> dict:
    """Numbers for the status HUD (and the spoken summary)."""

    from torque.skills.security import PsutilProbe

    probe = probe or PsutilProbe()
    rate = rate or NetworkRate()

    # blocking=False (background monitors) reads the CPU since the previous call instead of waiting 0.3 s.
    cpu = psutil.cpu_percent(interval=0.3 if blocking else None)
    memory = psutil.virtual_memory()

    try:
        disk = psutil.disk_usage("C:\\" if psutil.WINDOWS else "/")
        disk_percent = round(disk.percent)
    except OSError:
        disk_percent = None

    down, up = rate.read()

    return {
        "kind": "status",
        "cpu": round(cpu),
        "memory": round(memory.percent),
        "disk": disk_percent,
        "battery": _battery(),
        "network": {"down": round(down), "up": round(up)},
        "top": [{"name": n, "cpu": round(v)} for n, v in probe.top_processes("cpu", 3)],
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


def spoken_status(status: dict) -> str:

    text = f"CPU at {status['cpu']} percent, memory at {status['memory']} percent"

    battery = status.get("battery")

    if battery:
        text += f", battery at {battery['percent']} percent" + (" and charging" if battery["plugged"] else "")

    return text + "."
