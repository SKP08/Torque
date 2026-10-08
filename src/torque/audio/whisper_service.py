from faster_whisper import WhisperModel
from loguru import logger


class WhisperService:

    def __init__(self):

        logger.info("Loading Whisper model...")

        self.model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )

        logger.success("Whisper model loaded.")

    def transcribe(self, audio_path):

        logger.info(f"Transcribing: {audio_path}")

        segments, info = self.model.transcribe(
            audio_path,
            language="en",
            vad_filter=True,
            beam_size=5,
        )

        text = " ".join(
            segment.text.strip()
            for segment in segments
        ).strip()

        logger.info(
            f"Detected language: {info.language} "
            f"({info.language_probability:.2%})"
        )

        logger.success(f"Recognized: {text}")

        return text