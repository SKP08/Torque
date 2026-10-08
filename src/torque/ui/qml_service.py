import sys

from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

from torque.system.service import Service


class QMLService(Service):

    @property
    def name(self):
        return "QML Service"

    def initialize(self):

        self.app = QGuiApplication.instance()

        if self.app is None:
            self.app = QGuiApplication(sys.argv)

        self.engine = QQmlApplicationEngine()

        self.engine.load("src/torque/ui/qml/Main.qml")

        if not self.engine.rootObjects():
            raise RuntimeError("Failed to load Main.qml")

    def run(self):
        self.app.exec()