import os

import numpy as np
from loguru import logger

from torque.system.config_service import load_config

SAMPLE_RATE = 16000

# Nudges the recogniser to spell the name correctly. Deliberately just the
# name: Whisper sometimes "hallucinates" its own prompt from background
# noise, and a prompt like "Hey Torque. Open Chrome." could then trigger a
# real command by itself.
INITIAL_PROMPT = "Torque."

# Whisper tends to invent these from near-silence.
HALLUCINATIONS = {"you", "thank you", "thanks", "thanks for watching", "bye", "bye bye"}


def _cpu_threads() -> int:

    try:
        import psutil

        cores = psutil.cpu_count(logical=False) or os.cpu_count() or 4

    except ImportError:
        cores = os.cpu_count() or 4

    return max(2, min(8, cores))


class WhisperService:
    """
    faster-whisper tuned for short voice commands: English-only model,
    greedy decoding, no second VAD pass (the microphone already trimmed the
    audio), no timestamps. A throw-away transcription at start-up pays the
    one-off initialisation cost before the first real request.
    """

    MIN_SECONDS = 0.3

    def __init__(self, model=None, model_name=None, device=None):

        config = load_config()

        self.model_name = model_name or config["whisper_model"]
        self.device = "injected"

        if model is not None:
            self.model = model
            return

        self.model = self._load(self.model_name, device or config["whisper_device"])

    def _load(self, name: str, device: str):

        from faster_whisper import WhisperModel

        attempts = []

        if device in ("cuda", "auto"):
            attempts.append(("cuda", "float16"))

        attempts.append(("cpu", "int8"))

        logger.info(f"Loading Whisper model '{name}'...")

        last_error = None

        for dev, compute in attempts:

            try:
                model = WhisperModel(
                    name,
                    device=dev,
                    compute_type=compute,
                    cpu_threads=_cpu_threads(),
                )

                self._warm_up(model)

                self.device = dev

                logger.success(f"Whisper '{name}' ready on {dev}.")

                return model

            except Exception as error:  # noqa: BLE001
                last_error = error
                logger.warning(f"Whisper on {dev} failed ({error}).")

        raise RuntimeError(
            f"Could not load the Whisper model '{name}'. The first run needs "
            f"internet access to download it. ({last_error})"
        ) from last_error

    @staticmethod
    def _warm_up(model):

        segments, _ = model.transcribe(
            np.zeros(SAMPLE_RATE, dtype=np.float32),
            language="en",
            beam_size=1,
            without_timestamps=True,
        )

        list(segments)       # transcription is lazy: actually run it

    def transcribe(self, audio) -> str:
        """Transcribe float32 16 kHz mono audio (numpy array)."""

        duration = len(audio) / SAMPLE_RATE

        if duration < self.MIN_SECONDS:
            return ""

        segments, _ = self.model.transcribe(
            audio,
            language="en",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=False,
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=INITIAL_PROMPT,
        )

        kept = []

        for segment in segments:

            # Skip segments Whisper itself doubts are speech.
            if segment.no_speech_prob > 0.6 and segment.avg_logprob < -1.0:
                continue

            kept.append(segment.text.strip())

        text = " ".join(kept).strip()

        if duration < 1.5 and text.lower().strip(" .,!?") in HALLUCINATIONS:
            logger.debug("Dropped likely hallucination.")
            return ""

        return text
