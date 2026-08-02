import pystray
from PIL import Image, ImageDraw


class TorqueTray:

    def __init__(self):
        self.icon = pystray.Icon(
            "Torque",
            self._create_icon(),
            "Torque",
            menu=pystray.Menu(
                pystray.MenuItem("Open", self.open_window),
                pystray.MenuItem("Settings", self.settings),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.exit),
            ),
        )

    def run(self):
        self.icon.run()

    def stop(self):
        self.icon.stop()

    def open_window(self, icon, item):
        print("Open clicked")

    def settings(self, icon, item):
        print("Settings clicked")

    def exit(self, icon, item):
        self.stop()

    def _create_icon(self):
        image = Image.new("RGB", (64, 64), (25, 25, 25))
        draw = ImageDraw.Draw(image)

        draw.ellipse((12, 12, 52, 52), fill=(0, 170, 255))

        return image