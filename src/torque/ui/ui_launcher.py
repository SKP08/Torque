import subprocess
from pathlib import Path

from loguru import logger


class UILauncher:

    def __init__(self):
        self.process = None

    def start(self):
        # ui_launcher.py is in:
        # src/torque/ui/ui_launcher.py
        # We want:
        # D:/Torque/workspace/torque

        project_root = Path(__file__).resolve().parents[3]

        ui_path = project_root / "torque-ui"

        logger.info(f"Launching React UI from: {ui_path}")

        self.process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(ui_path),
            shell=True,
        )