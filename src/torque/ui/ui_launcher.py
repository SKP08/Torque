import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from loguru import logger

from torque.paths import LOGS_DIR, UI_DIR
from torque.system.config_service import load_config

IS_WINDOWS = sys.platform == "win32"


class UILauncher:
    """
    Starts the React UI dev server and opens it in a frameless app window
    (Edge/Chrome --app mode), falling back to the default browser.
    """

    def __init__(self):
        self.process = None
        self._log_file = None

    # ----------------------------------------------------------

    def start(self):

        config = load_config()

        self.url = config["ui_url"]

        npm = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")

        if not npm:
            logger.warning("npm not found; the UI was not started. Install Node.js.")
            return

        if not (UI_DIR / "node_modules").exists():
            logger.warning(
                f"UI dependencies missing. Run 'npm install' in {UI_DIR} first."
            )
            return

        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        self._log_file = open(LOGS_DIR / "ui.log", "ab")

        logger.info(f"Launching React UI from: {UI_DIR}")

        self.process = subprocess.Popen(
            [npm, "run", "dev"],
            cwd=str(UI_DIR),
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
        )

        if config["ui_window"]:
            threading.Thread(
                target=self._open_when_ready,
                name="TorqueUIOpen",
                daemon=True,
            ).start()

    def _open_when_ready(self):

        parsed = urlparse(self.url)

        host = parsed.hostname or "localhost"
        port = parsed.port or 80

        deadline = time.monotonic() + 30

        while time.monotonic() < deadline:

            if self.process and self.process.poll() is not None:
                logger.error("UI dev server exited early; see logs/ui.log")
                return

            try:
                with socket.create_connection((host, port), timeout=1):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            logger.warning("UI dev server did not become ready in time.")
            return

        self.open_window()

    # ----------------------------------------------------------

    @staticmethod
    def _find_browser() -> str | None:

        candidates = []

        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):

            base = os.environ.get(env)

            if not base:
                continue

            candidates.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
            candidates.append(Path(base) / "Google/Chrome/Application/chrome.exe")

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

        return shutil.which("msedge") or shutil.which("chrome")

    def open_window(self):

        url = getattr(self, "url", None) or load_config()["ui_url"]

        browser = self._find_browser()

        if browser:
            subprocess.Popen([browser, f"--app={url}", "--window-size=520,620"])
            return

        webbrowser.open(url)

    # ----------------------------------------------------------

    def stop(self):

        process = self.process

        if process and process.poll() is None:

            try:
                if IS_WINDOWS:
                    # npm spawns child processes; kill the whole tree.
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()

            except Exception:  # noqa: BLE001
                logger.exception("Could not stop the UI process.")

        if self._log_file:
            self._log_file.close()
            self._log_file = None

        self.process = None
