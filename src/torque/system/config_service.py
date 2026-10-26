import json

from loguru import logger

from torque.paths import CONFIG_PATH
from torque.system.service import Service

DEFAULT_CONFIG = {
    "assistant_name": "Torque",
    "theme": "dark",
    "voice_enabled": True,
    "notifications": True,

    # Input
    "hotkey": "ctrl+space",
    "hotkey_suppress": False,
    "wake_word_enabled": True,
    "chime_enabled": True,
    "pc_control_enabled": True,
    "security_skills_enabled": True,
    "screen_enabled": True,
    "hud_enabled": True,
    "hud_hold_seconds": 10,
    "home_location": None,
    "filler_after_seconds": 1.5,
    "barge_in_enabled": False,
    "voice_lock_enabled": False,
    "voice_lock_threshold": 0.5,
    "context_enabled": True,
    "routines_enabled": True,
    "desktop_control_enabled": False,
    "browser_enabled": True,
    "browser_channel": "msedge",
    "browser_headless": False,
    "timers_enabled": True,
    "alerts_enabled": True,
    "alert_speech": True,
    "alert_categories": ["battery", "cpu", "memory", "disk", "ports"],
    "agent_enabled": True,
    "agent_model": "qwen3:4b",
    "agent_max_steps": 8,
    "phone_enabled": False,
    "phone_host": "0.0.0.0",
    "phone_port": 8766,

    # Conversation timing (seconds)
    "listen_timeout": 10.0,
    "followup_timeout": 7.0,
    "end_of_speech_silence": 0.9,
    "end_of_speech_silence_short": 0.5,

    # Models
    "llm_model": "qwen2.5:3b",
    "llm_num_predict": 200,
    "llm_num_ctx": 2048,
    "whisper_model": "base.en",
    "whisper_device": "cpu",
    "piper_voice": "en_US-lessac-medium",
    "tts_engine": "auto",
    "kokoro_model": "kokoro-v1.0.int8.onnx",
    "kokoro_voice": "bm_george",
    "kokoro_language": "en-gb",
    "tts_speed": 1.0,
    "persona": "butler",
    "user_title": "",
    "web_search_depth": "basic",

    # Transport / UI
    "ws_host": "localhost",
    "ws_port": 8765,
    "ui_mode": "overlay",
    "ui_port": 5174,
    "overlay_position": "bottom",
    "tray_enabled": True,
}

_cache: dict | None = None


def load_config(force: bool = False) -> dict:
    """
    Return the effective configuration: defaults overlaid with
    config/settings.json. Missing or invalid files fall back to defaults.
    """

    global _cache

    if _cache is not None and not force:
        return _cache

    config = dict(DEFAULT_CONFIG)

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as file:
                user = json.load(file)

            if isinstance(user, dict):
                config.update(user)
            else:
                logger.warning("settings.json is not an object; using defaults.")

        except (OSError, json.JSONDecodeError) as error:
            logger.warning(f"Could not read settings.json ({error}); using defaults.")

    _cache = config

    return config


class ConfigService(Service):
    """
    Loads and manages Torque configuration.
    """

    CONFIG_PATH = CONFIG_PATH

    @property
    def name(self) -> str:
        return "Configuration Service"

    def initialize(self):

        self.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

        if not self.CONFIG_PATH.exists():

            with open(self.CONFIG_PATH, "w", encoding="utf-8") as file:
                json.dump(DEFAULT_CONFIG, file, indent=4)

            logger.info("Created default configuration.")

        self.config = load_config(force=True)

        logger.info("Configuration loaded.")

    def load(self) -> dict:
        return load_config()
