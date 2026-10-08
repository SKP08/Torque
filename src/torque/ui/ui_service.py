import sys

from PySide6.QtWidgets import QApplication

from torque.system.service import Service
from torque.ui.overlay import Overlay


class UIService(Service):

    @property
    def name(self):
        return "UI Service"

    def initialize(self):

        self.app = QApplication.instance()

        if self.app is None:
            self.app = QApplication(sys.argv)

        self.overlay = Overlay()

    def run(self):
        self.app.exec()