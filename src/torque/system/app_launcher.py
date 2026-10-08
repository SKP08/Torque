import os
import subprocess

from loguru import logger

from torque.system.app_matcher import AppMatcher


class AppLauncher:

    def __init__(self):

        self.matcher = AppMatcher()
        self.matcher.load()

    # ==========================================================
    # OPEN APPLICATION
    # ==========================================================

    def launch(self, query: str) -> bool:

        app = self.matcher.match(query)

        if not app:

            logger.warning(
                f"Application not found: {query}"
            )

            return False

        try:

            logger.info(
                f"Launching {app['name']}"
            )

            os.startfile(
                app["shortcut"]
            )

            logger.success(
                f"Launched {app['name']}"
            )

            return True

        except Exception as e:

            logger.exception(e)

            return False

    # ==========================================================
    # CLOSE APPLICATION
    # ==========================================================

    def close(self, query: str) -> bool:

        app = self.matcher.match(query)

        if not app:

            logger.warning(
                f"Application not found: {query}"
            )

            return False

        app_name = app["name"]

        logger.info(
            f"Attempting to close {app_name}"
        )

        executable = self._get_executable_name(
            app_name
        )

        if not executable:

            logger.warning(
                f"Could not determine executable "
                f"for {app_name}"
            )

            return False

        logger.info(
            f"Detected process: {executable}"
        )

        try:

            result = subprocess.run(
                [
                    "taskkill",
                    "/IM",
                    executable,
                    "/T",
                    "/F",
                ],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            if result.returncode == 0:

                logger.success(
                    f"Closed {app_name}"
                )

                return True

            logger.warning(
                result.stdout.strip()
                or result.stderr.strip()
            )

            return False

        except Exception as e:

            logger.exception(e)

            return False

    # ==========================================================
    # PROCESS NAME MAPPING
    # ==========================================================

    def _get_executable_name(
        self,
        app_name: str,
    ) -> str | None:

        app_name = app_name.lower().strip()

        known_processes = {

            "google chrome": "chrome.exe",
            "chrome": "chrome.exe",

            "microsoft edge": "msedge.exe",
            "edge": "msedge.exe",

            "discord": "Discord.exe",

            "file explorer": "explorer.exe",
            "explorer": "explorer.exe",

            "notepad": "notepad.exe",

            "firefox": "firefox.exe",

            "brave": "brave.exe",

            "visual studio code": "Code.exe",
            "vs code": "Code.exe",
        }

        return known_processes.get(app_name)