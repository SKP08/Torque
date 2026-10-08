import time

from PySide6.QtCore import QObject, QTimer


class Renderer(QObject):

    FPS = 60

    def __init__(self, widget):
        super().__init__()

        self.widget = widget

        self.last_time = time.perf_counter()

        self.timer = QTimer()

        self.timer.timeout.connect(self.tick)

    def start(self):
        self.timer.start(int(1000 / self.FPS))

    def tick(self):

        now = time.perf_counter()

        delta = now - self.last_time

        self.last_time = now

        if hasattr(self.widget, "update_scene"):
            self.widget.update_scene(delta)

        self.widget.update()