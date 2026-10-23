import os

import pystray
from PIL import Image, ImageDraw

from torque.paths import CONFIG_PATH


class TorqueTray:
    """
    System tray icon. Blocks in run(), so it owns the main thread.
    """

    def __init__(self, on_open=None, on_exit=None):

        self._on_open = on_open
        self._on_exit = on_exit

        self.icon = pystray.Icon(
            "Torque",
            self._create_icon(),
            "Torque",
            menu=pystray.Menu(
                pystray.MenuItem("Open UI", self._open, default=True),
                pystray.MenuItem("Edit settings", self._settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self._exit),
            ),
        )

    def run(self):
        self.icon.run()

    def stop(self):
        self.icon.stop()

    def _open(self, icon, item):
        if self._on_open:
            self._on_open()

    def _settings(self, icon, item):
        if hasattr(os, "startfile"):
            os.startfile(CONFIG_PATH)

    def _exit(self, icon, item):
        if self._on_exit:
            self._on_exit()
        self.stop()

    @staticmethod
    def _create_icon():
        image = Image.new("RGB", (64, 64), (25, 25, 25))
        draw = ImageDraw.Draw(image)

        draw.ellipse((12, 12, 52, 52), fill=(0, 170, 255))

        return image
