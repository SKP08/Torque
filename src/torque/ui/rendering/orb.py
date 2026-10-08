import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient

from torque.ui.rendering.updatable import Updatable


class Orb(Updatable):

    def __init__(self):

        self.time = 0.0

        self.radius = 34

        self.glow_radius = 95

    def update(self, delta_time: float):

        self.time += delta_time

    def draw(self, painter: QPainter, center: QPointF):

        pulse = (math.sin(self.time * 2.0) + 1.0) * 0.5

        radius = self.radius + pulse * 3

        glow = QRadialGradient(center, self.glow_radius)

        glow.setColorAt(0.0, QColor(0, 170, 255, 180))
        glow.setColorAt(0.45, QColor(0, 170, 255, 70))
        glow.setColorAt(1.0, QColor(0, 170, 255, 0))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, self.glow_radius, self.glow_radius)

        orb = QRadialGradient(center, radius)

        orb.setColorAt(0.0, QColor(255, 255, 255))
        orb.setColorAt(0.35, QColor(90, 220, 255))
        orb.setColorAt(1.0, QColor(0, 120, 255))

        painter.setBrush(QBrush(orb))
        painter.drawEllipse(center, radius, radius)