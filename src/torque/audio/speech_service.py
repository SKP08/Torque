from loguru import logger

from torque.audio.microphone import MicrophoneService
from torque.audio.whisper_service import WhisperService


class SpeechService:

    def __init__(self):

        self.microphone = MicrophoneService()
        self.whisper = WhisperService()

    def listen(self, timeout=None):
        """
        Returns the transcript, "" if speech was heard but not recognised,
        or None if nobody spoke before `timeout` / the recording was cancelled.
        """

        logger.info("Listening...")

        audio = self.microphone.record(timeout=timeout)

        if audio is None:
            return None

        return self.whisper.transcribe(audio).strip()

    def stop(self):
        self.microphone.stop()

    def reset(self):
        self.microphone.reset()
