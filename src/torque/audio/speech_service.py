from loguru import logger

from torque.audio.microphone import MicrophoneService
from torque.audio.whisper_service import WhisperService


class SpeechService:

    def __init__(self):

        self.microphone = MicrophoneService()
        self.whisper = WhisperService()

    def listen(self) -> str:

        logger.info("Listening...")

        audio_path = self.microphone.record()

        # Recording may be cancelled or contain no audio.
        if not audio_path:

            logger.warning(
                "No audio recording was produced."
            )

            return ""

        text = self.whisper.transcribe(
            audio_path
        )

        # Always return a clean string.
        if not text:

            return ""

        return text.strip()

    def stop(self):

        logger.info("Stopping speech service...")

        self.microphone.stop()

    def reset(self):

        logger.info("Resetting speech service...")

        self.microphone.reset()