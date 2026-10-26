"""
What is the user looking at right now: the foreground window's app and title.

Read-only and local. Windows only (ctypes); elsewhere it reports nothing.
Windows that probably show secrets are reported as "a private window" so their
titles never reach the language model or the logs.
"""

import re
import sys
from dataclasses import dataclass

PRIVATE = re.compile(
    r"keepass|bitwarden|1password|lastpass|dashlane|proton pass|authenticator|"
    r"incognito|inprivate|private browsing|private window|password",
    re.IGNORECASE,
)

FRIENDLY = {
    "chrome.exe": "Chrome", "msedge.exe": "Edge", "firefox.exe": "Firefox", "code.exe": "VS Code",
    "explorer.exe": "File Explorer", "spotify.exe": "Spotify", "discord.exe": "Discord",
    "winword.exe": "Word", "excel.exe": "Excel", "powerpnt.exe": "PowerPoint", "outlook.exe": "Outlook",
    "windowsterminal.exe": "Terminal", "powershell.exe": "PowerShell", "cmd.exe": "Command Prompt",
    "notepad.exe": "Notepad", "teams.exe": "Teams", "slack.exe": "Slack", "pycharm64.exe": "PyCharm",
}


@dataclass
class WindowContext:
    process: str = ""
    title: str = ""
    private: bool = False

    @property
    def app(self) -> str:
        name = self.process.lower()

        return FRIENDLY.get(name) or re.sub(r"\.exe$", "", self.process, flags=re.IGNORECASE).title()

    def describe(self) -> str:
        """For the model: 'Chrome - Kerberos - Wikipedia'."""

        if self.private:
            return f"{self.app} (a private window)" if self.app else "a private window"

        return f"{self.app} - {self.title}" if self.title else self.app

    def spoken(self) -> str:
        if self.private:
            return "You're in a private window, so I'll leave it alone."

        if not self.app:
            return "I can't tell which window is active."

        if self.title and self.title.lower() != self.app.lower():
            return f"You're in {self.app}, on {self.title[:80]}."

        return f"You're in {self.app}."


def classify(process: str, title: str) -> WindowContext:
    title = (title or "").strip()
    private = bool(PRIVATE.search(f"{process} {title}"))

    return WindowContext(process or "", "" if private else title, private)


def _foreground_windows():
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()

    if not hwnd:
        return "", ""

    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    try:
        process = psutil.Process(pid.value).name()
    except (psutil.Error, ValueError):
        process = ""

    return process, buffer.value


def active_window(provider=None) -> WindowContext | None:
    """The foreground window, or None when it can't be read. `provider` is for tests."""

    try:
        if provider is None:
            if sys.platform != "win32":
                return None

            provider = _foreground_windows

        process, title = provider()

    except Exception:  # noqa: BLE001
        return None

    if not process and not title:
        return None

    return classify(process, title)
