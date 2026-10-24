import time
from dataclasses import dataclass

CATEGORIES = ("battery", "cpu", "memory", "disk", "ports")


@dataclass
class Alert:
    category: str
    message: str
    severity: str = "warn"          # "info" or "warn"


class AlertMonitor:
    """
    Watches the PC and returns an Alert when something deserves your attention.

    status_fn() -> dict from hud.status.system_status; ports_fn() -> [(port, process, exposed)].
    CPU and memory must stay high for `sustain` checks in a row, every alert has a
    cooldown, and a new open port is reported once.
    """

    COOLDOWNS = {"battery": 900, "cpu": 600, "memory": 600, "disk": 3600}

    def __init__(self, status_fn, ports_fn=None, categories=CATEGORIES, sustain=3,
                 clock=time.monotonic, battery_low=20, battery_critical=8,
                 cpu_high=90, memory_high=92, disk_high=95):
        self.status_fn = status_fn
        self.ports_fn = ports_fn
        self.categories = set(categories)
        self.sustain = sustain
        self.clock = clock
        self.limits = dict(battery_low=battery_low, battery_critical=battery_critical,
                           cpu=cpu_high, memory=memory_high, disk=disk_high)
        self._streak = {"cpu": 0, "memory": 0}
        self._last = {}
        self._ports = None

    def _cooled(self, key, cooldown):
        now = self.clock()

        if key in self._last and now - self._last[key] < cooldown:
            return False

        self._last[key] = now
        return True

    def check(self) -> list:
        alerts = []

        try:
            status = self.status_fn()
        except Exception:  # noqa: BLE001
            status = None

        if status:
            alerts += self._battery(status)
            alerts += self._sustained("cpu", status, "CPU", top=True)
            alerts += self._sustained("memory", status, "Memory", top=False)
            alerts += self._disk(status)

        alerts += self._new_ports()

        return alerts

    def _battery(self, status):
        battery = status.get("battery")

        if "battery" not in self.categories or not battery or battery.get("plugged"):
            return []

        pct = battery["percent"]

        if pct <= self.limits["battery_critical"] and self._cooled("battery-critical", self.COOLDOWNS["battery"]):
            return [Alert("battery", f"Battery critically low at {pct} percent. Plug in now.")]

        if pct <= self.limits["battery_low"] and pct > self.limits["battery_critical"] \
                and self._cooled("battery", self.COOLDOWNS["battery"]):
            return [Alert("battery", f"Battery is at {pct} percent. You may want to plug in.", "info")]

        return []

    def _sustained(self, key, status, label, top):
        if key not in self.categories:
            return []

        value = status.get(key)

        if value is None or value < self.limits[key]:
            self._streak[key] = 0
            return []

        self._streak[key] += 1

        if self._streak[key] < self.sustain or not self._cooled(key, self.COOLDOWNS[key]):
            return []

        message = f"{label} has been at {value} percent for a while."

        if top and status.get("top"):
            message += f" {status['top'][0]['name']} is the busiest."

        return [Alert(key, message)]

    def _disk(self, status):
        disk = status.get("disk")

        if "disk" not in self.categories or disk is None or disk < self.limits["disk"]:
            return []

        if not self._cooled("disk", self.COOLDOWNS["disk"]):
            return []

        return [Alert("disk", f"Your disk is {disk} percent full.")]

    def _new_ports(self):
        if "ports" not in self.categories or not self.ports_fn:
            return []

        try:
            current = {(port, name) for port, name, exposed in self.ports_fn() if exposed}
        except Exception:  # noqa: BLE001
            return []

        if self._ports is None:             # first look is the baseline, not an alert
            self._ports = current
            return []

        new = sorted(current - self._ports)
        self._ports |= current

        return [Alert("ports", f"{name} just opened port {port} to your network.")
                for port, name in new[:2]]
