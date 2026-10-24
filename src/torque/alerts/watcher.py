import threading
import time

from loguru import logger


def timer_message(item) -> str:
    label = item.get("label") or ""

    if item.get("kind") == "reminder":
        return f"Reminder: {label}." if label else "Reminder."

    return f"Your {label} timer is up." if label else "Your timer is up."


class AlertWatcher:
    """
    Background thread: announces timers when they come due and runs the monitors.

    announce(message, severity, speak) is supplied by the controller; it shows
    the toast and speaks only when Torque isn't already in a conversation.
    """

    def __init__(self, store, announce, monitor=None, interval=1.0, monitor_every=20.0,
                 clock=time.monotonic, on_tick=None):
        self.store = store
        self.announce = announce
        self.monitor = monitor
        self.interval = interval
        self.monitor_every = monitor_every
        self.clock = clock
        self.on_tick = on_tick
        self._next_monitor = 0.0
        self._stop = threading.Event()
        self._thread = None

    def tick(self):
        """One pass; returns the number of announcements made (for tests)."""

        count = 0

        for item in self.store.pop_due():
            self.announce(timer_message(item), "info", True)
            count += 1

        if self.monitor and self.clock() >= self._next_monitor:
            self._next_monitor = self.clock() + self.monitor_every

            for alert in self.monitor.check():
                self.announce(alert.message, alert.severity, True)
                count += 1

        if self.on_tick:
            self.on_tick()

        return count

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="TorqueAlerts", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("Alert watcher error.")
