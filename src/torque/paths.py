"""Single source of truth for every filesystem location Torque uses.

Everything is anchored to the repository root (not the current working
directory), so Torque behaves the same no matter where it is launched from.
"""

from pathlib import Path

# src/torque/paths.py -> parents[2] is the repository root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"
MODELS_DIR = PROJECT_ROOT / "models"
CONFIG_DIR = PROJECT_ROOT / "config"
UI_DIR = PROJECT_ROOT / "torque-ui"

CONFIG_PATH = CONFIG_DIR / "settings.json"
MEMORY_DB = DATA_DIR / "memory.db"
APPS_CACHE = DATA_DIR / "apps.json"
PHONE_TOKEN = DATA_DIR / "phone_token.txt"


def ensure_dirs() -> None:
    for directory in (DATA_DIR, LOGS_DIR, CONFIG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
