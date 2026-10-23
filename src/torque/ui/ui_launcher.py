import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from loguru import logger

from torque.paths import HUD_CACHE, LOGS_DIR, UI_DIR
from torque.system.config_service import load_config
from torque.ui.static_server import StaticServer

IS_WINDOWS = sys.platform == "win32"

BUILD_TIMEOUT = 180


def find_electron(ui_dir: Path = UI_DIR) -> Path | None:
    """The Electron binary installed by `npm install` in torque-ui, if any."""

    package = ui_dir / "node_modules" / "electron"
    marker = package / "path.txt"

    try:
        relative = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    binary = package / "dist" / relative

    return binary if binary.exists() else None


def build_is_stale(ui_dir: Path = UI_DIR) -> bool:
    """True if torque-ui/dist is missing or older than the sources."""

    index = ui_dir / "dist" / "index.html"

    if not index.exists():
        return True

    built = index.stat().st_mtime

    watched = [ui_dir / "index.html", ui_dir / "package.json", ui_dir / "vite.config.js"]
    watched += (ui_dir / "src").rglob("*") if (ui_dir / "src").exists() else []

    return any(p.is_file() and p.stat().st_mtime > built for p in watched)


class UILauncher:
    """
    Serves the React UI and shows it.

    ui_mode "overlay": a transparent always-on-top Electron window that pops
                       up when Torque is active (the Siri-style card).
    ui_mode "window":  a normal frameless Edge/Chrome app window.
    ui_mode "none":    nothing; the UI is still reachable in a browser tab.

    If Electron isn't installed the overlay falls back to the app window.
    """

    def __init__(self):
        self.server = None
        self.process = None
        self.url = None
        self._log_file = None

    # ----------------------------------------------------------

    def start(self):

        config = load_config()

        mode = config["ui_mode"]

        if mode == "none":
            return

        if not self._ensure_built():
            return

        self.server = StaticServer(
            UI_DIR / "dist", config["ui_port"], mounts={"/cache": HUD_CACHE}
        )

        if not self.server.start():
            self.server = None
            return

        self.url = self.server.url

        if mode == "overlay":
            if self._start_overlay(config):
                return

            logger.warning(
                "Electron isn't installed (run 'npm install' in torque-ui); "
                "using a normal app window instead."
            )

        self.open_window()

    def _ensure_built(self) -> bool:

        if not build_is_stale():
            return True

        npm = shutil.which("npm.cmd" if IS_WINDOWS else "npm") or shutil.which("npm")

        if not npm or not (UI_DIR / "node_modules").exists():
            logger.warning(
                f"UI not built. Install Node.js, then run 'npm install' and "
                f"'npm run build' in {UI_DIR}."
            )
            return (UI_DIR / "dist" / "index.html").exists()

        logger.info("Building the UI (first run, or sources changed)...")

        try:
            result = subprocess.run(
                [npm, "run", "build"],
                cwd=str(UI_DIR),
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired):
            logger.exception("UI build failed.")
            return (UI_DIR / "dist" / "index.html").exists()

        if result.returncode != 0:
            logger.error(f"UI build failed:\n{result.stdout[-800:]}{result.stderr[-800:]}")
            return (UI_DIR / "dist" / "index.html").exists()

        return True

    def _start_overlay(self, config) -> bool:

        electron = find_electron()

        if not electron:
            return False

        LOGS_DIR.mkdir(parents=True, exist_ok=True)

        self._log_file = open(LOGS_DIR / "ui.log", "ab")

        env = {
            **os.environ,
            "TORQUE_UI_URL": self.url,
            "TORQUE_OVERLAY_POSITION": config["overlay_position"],
        }

        # Electron must not run as plain node.
        env.pop("ELECTRON_RUN_AS_NODE", None)

        self.process = subprocess.Popen(
            [str(electron), str(UI_DIR)],
            cwd=str(UI_DIR),
            env=env,
            stdout=self._log_file,
            stderr=subprocess.STDOUT,
        )

        logger.info("Overlay started.")

        return True

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
        """A normal (non-overlay) window with the UI."""

        if not self.url:
            logger.info("The UI isn't running.")
            return

        browser = self._find_browser()

        if browser:
            subprocess.Popen([browser, f"--app={self.url}", "--window-size=560,300"])
            return

        webbrowser.open(self.url)

    # ----------------------------------------------------------

    def stop(self):

        process = self.process

        if process and process.poll() is None:

            try:
                if IS_WINDOWS:
                    # Electron spawns helper processes; kill the whole tree.
                    subprocess.run(
                        ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True,
                        check=False,
                    )
                else:
                    process.terminate()

            except Exception:  # noqa: BLE001
                logger.exception("Could not stop the overlay.")

        if self._log_file:
            self._log_file.close()
            self._log_file = None

        if self.server:
            self.server.stop()
            self.server = None

        self.process = None
