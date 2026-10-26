"""
Watches the places malware hides to survive a reboot: startup entries, scheduled
tasks and the hosts file. Read-only: it reports changes, it never removes anything.

The first look is saved as a baseline (data/security_baseline.json); later looks
are compared with it, so a change made while Torque was closed is still caught.
Sources are plain callables so tests (and non-Windows machines) use fakes.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

from torque.alerts.monitors import Alert

HOSTS_PATH = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

RUN_KEYS = (
    (r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
    (r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
    (r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU"),
)

# Entries the OS creates itself; reporting them would just be noise.
BENIGN_TASK = re.compile(r"^\\Microsoft\\|^\\(?:OneDrive|Google|MicrosoftEdge|Adobe|Mozilla)", re.IGNORECASE)


def startup_entries() -> dict:
    """{'Run: OneDrive': 'C:\\...\\OneDrive.exe', 'Folder: x.lnk': '...'} (Windows only)."""

    found = {}

    if sys.platform != "win32":
        return found

    import winreg

    hives = {"HKCU": winreg.HKEY_CURRENT_USER, "HKLM": winreg.HKEY_LOCAL_MACHINE}

    for key_path, hive in RUN_KEYS:
        try:
            with winreg.OpenKey(hives[hive], key_path) as key:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, i)
                    found[f"{hive} {key_path.rsplit(chr(92), 1)[-1]}: {name}"] = str(value)
        except OSError:
            continue

    folders = [Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup",
               Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs/StartUp"]

    for folder in folders:
        try:
            for item in folder.iterdir():
                if item.name.lower() != "desktop.ini":
                    found[f"Startup folder: {item.name}"] = str(item)
        except OSError:
            continue

    return found


def scheduled_tasks() -> dict:
    """{task name: run-as/next info} for non-Microsoft tasks (Windows only)."""

    if sys.platform != "win32":
        return {}

    try:
        out = subprocess.run(["schtasks", "/query", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return {}

    tasks = {}

    for line in out.splitlines():
        name = line.split('","')[0].strip('"')

        if name.startswith("\\") and not BENIGN_TASK.match(name):
            tasks[f"Task: {name}"] = ""

    return tasks


def hosts_lines(path=HOSTS_PATH) -> list:
    """The active (non-comment) lines of the hosts file, normalised."""

    try:
        text = Path(path).read_text(errors="ignore")
    except OSError:
        return []

    lines = []

    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()

        if line:
            lines.append(" ".join(line.split()))

    return sorted(set(lines))


def default_sources():
    return {"startup": lambda: {**startup_entries(), **scheduled_tasks()}, "hosts": hosts_lines}


def hosts_concern(line: str) -> str:
    """Plain-English reason a hosts line deserves attention ('' if it looks routine)."""

    parts = line.split()

    if len(parts) < 2:
        return ""

    address, names = parts[0], parts[1:]

    if address in ("127.0.0.1", "0.0.0.0", "::1") and all(not re.search(r"bank|paypal|google|microsoft|apple|amazon", n) for n in names):
        return "blocks a site (common for ad blockers)"

    return f"sends {names[0]} to {address}, which can redirect you to a fake site"


class PersistenceWatch:
    """check() -> [Alert] for startup/task additions and hosts-file changes since the baseline."""

    def __init__(self, store_path, sources=None, every=300.0, clock=time.monotonic):
        self.store_path = Path(store_path)
        self.sources = sources or default_sources()
        self.every = every
        self.clock = clock
        self._next = 0.0
        self.baseline = self._load()

    def _load(self):
        try:
            return json.loads(self.store_path.read_text())
        except (OSError, ValueError):
            return None

    def _save(self):
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(json.dumps(self.baseline, indent=1))
        except OSError:
            logger.debug("Could not save the security baseline.", exc_info=True)

    def snapshot(self) -> dict:
        startup = self.sources["startup"]()
        hosts = self.sources["hosts"]()

        return {"startup": dict(startup), "hosts": list(hosts)}

    def diff(self, now=None):
        """(new startup entries {name: command}, new hosts lines [..], removed hosts lines [..])."""

        now = now or self.snapshot()
        old = self.baseline or {"startup": {}, "hosts": []}

        added = {k: v for k, v in now["startup"].items() if k not in old["startup"]}
        new_hosts = [line for line in now["hosts"] if line not in old["hosts"]]
        gone = [line for line in old["hosts"] if line not in now["hosts"]]

        return added, new_hosts, gone

    def check(self) -> list:
        if self.clock() < self._next:
            return []

        self._next = self.clock() + self.every

        try:
            now = self.snapshot()
        except Exception:  # noqa: BLE001
            logger.debug("Security snapshot failed.", exc_info=True)
            return []

        if self.baseline is None:                        # first look: remember, don't alarm
            self.baseline = now
            self._save()
            return []

        added, new_hosts, _ = self.diff(now)
        alerts = []

        for name, command in list(added.items())[:2]:
            label = name.split(": ", 1)[-1]
            alerts.append(Alert("startup", f"New startup item: {label}. If you didn't install something, check it.", "warn"))

        for line in new_hosts[:2]:
            alerts.append(Alert("hosts", f"Your hosts file changed: {line.split()[1] if len(line.split()) > 1 else line} "
                                         f"now points to {line.split()[0]}. Programs normally don't do that.", "warn"))

        if added or new_hosts or now["hosts"] != self.baseline["hosts"]:
            # Accept the new state so each change is reported once; "review" answers still show it.
            self.baseline = {"startup": {**self.baseline["startup"], **now["startup"]}, "hosts": now["hosts"]}
            self._save()

        return alerts


def describe_startup(watch) -> str:
    """Spoken summary of what starts with the PC, and what's new since the baseline."""

    try:
        now = watch.snapshot()
    except Exception:  # noqa: BLE001
        return "I couldn't read the startup list."

    entries = now["startup"]

    if not entries:
        return "I don't see any startup items" + ("." if sys.platform == "win32" else " (this check only works on Windows).")

    added, _, _ = watch.diff(now)

    names = [k.split(": ", 1)[-1] for k in entries]
    text = f"{len(names)} things start with your PC, including {', '.join(names[:4])}."

    if watch.baseline is not None and added:
        text += f" New since I first looked: {', '.join(k.split(': ', 1)[-1] for k in list(added)[:3])}."
    elif watch.baseline is not None:
        text += " Nothing new since I first looked."

    return text


def describe_hosts(watch) -> str:
    lines = watch.sources["hosts"]()

    if not lines:
        return "Your hosts file has no custom entries, which is normal."

    odd = [(line, hosts_concern(line)) for line in lines]
    risky = [(line, why) for line, why in odd if why.startswith("sends")]

    if risky:
        line, why = risky[0]
        return f"Your hosts file has {len(lines)} entries, and one {why}: {line}. If you didn't add it, treat it as suspicious."

    return f"Your hosts file has {len(lines)} custom entries and they look routine, like site blocking."


# Short, honest explanations for processes people ask about.
KNOWN = {
    "svchost.exe": "a Windows host process that runs system services. Many copies is normal",
    "lsass.exe": "the Windows login security process. It should only live in the Windows folder",
    "csrss.exe": "a core Windows process",
    "explorer.exe": "the Windows desktop and file manager",
    "chrome.exe": "Google Chrome", "msedge.exe": "Microsoft Edge", "firefox.exe": "Firefox",
    "code.exe": "Visual Studio Code", "python.exe": "Python, possibly running Torque or a script",
    "node.exe": "Node.js, often a dev server", "ollama.exe": "the local AI model server Torque uses",
    "onedrive.exe": "OneDrive file sync", "spotify.exe": "Spotify", "discord.exe": "Discord",
    "searchhost.exe": "Windows search", "msmpeng.exe": "Microsoft Defender antivirus",
}


def explain_process(probe, name: str) -> str:
    name = name.strip().lower()
    exe = name if name.endswith(".exe") else name + ".exe"

    matches = [(n, p) for n, p in probe.processes() if n.lower() in (name, exe)]

    if not matches:
        return f"I don't see {name} running right now."

    from torque.skills.security import RISKY_PATH, SYSTEM_NAMES, SYSTEM_PATH

    proc, path = matches[0]
    text = f"{proc} is {KNOWN.get(proc.lower(), 'a program I do not recognise')}."

    if RISKY_PATH.search(path):
        text += " It is running from a temporary or downloads folder, which is unusual for a legitimate program."
    elif proc.lower() in SYSTEM_NAMES and not SYSTEM_PATH.search(path):
        text += " It has a Windows system name but isn't in the Windows folder, which is a classic disguise."
    elif proc.lower() not in KNOWN:
        text += " Unknown isn't the same as bad. Search the name online before doing anything."

    if len(matches) > 1:
        text += f" There are {len(matches)} copies running."

    return text
