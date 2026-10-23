from faster_whisper import WhisperModel
from loguru import logger

from torque.system.config_service import load_config

SAMPLE_RATE = 16000

# Nudges the recogniser toward words Torque actually hears.
INITIAL_PROMPT = "Torque. Open Chrome. Launch Spotify. Close Discord. Visual Studio Code."

# Whisper tends to invent these from near-silence.
HALLUCINATIONS = {"you", "thank you", "thanks", "thanks for watching", "bye"}


class WhisperService:

    MIN_SECONDS = 0.3

    def __init__(self, model=None):

        model_name = model or load_config()["whisper_model"]

        logger.info(f"Loading Whisper model '{model_name}'...")

        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
        )

        logger.success("Whisper model loaded.")

    def transcribe(self, audio) -> str:
        """Transcribe float32 16 kHz mono audio (numpy array)."""

        duration = len(audio) / SAMPLE_RATE

        if duration < self.MIN_SECONDS:
            return ""

        segments, info = self.model.transcribe(
            audio,
            language="en",
            vad_filter=True,
            beam_size=3,
            condition_on_previous_text=False,
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
            logger.debug(f"Dropped likely hallucination: '{text}'")
            return ""

        logger.success(f"Recognized: {text}")

        return text
