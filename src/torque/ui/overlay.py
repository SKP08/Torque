from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from torque.ui.rendering.orb import Orb
from torque.ui.rendering.renderer import Renderer


class Overlay(QWidget):

    def __init__(self):
        super().__init__()

        self.resize(500, 500)

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )

        self.setAttribute(Qt.WA_TranslucentBackground)

        screen = self.screen().availableGeometry()

        self.move(
            screen.center().x() - self.width() // 2,
            screen.center().y() - self.height() // 2,
        )

        self.orb = Orb()

        self.renderer = Renderer(self)
        self.renderer.start()

    def paintEvent(self, event):

        painter = QPainter(self)

        painter.setRenderHint(QPainter.Antialiasing)

        center = self.rect().center()

        self.orb.draw(
            painter,
            center,
        )

    def update_scene(self, delta):

        self.orb.update(delta)