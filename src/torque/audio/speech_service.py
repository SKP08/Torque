from loguru import logger

from torque.audio.microphone import MicrophoneService
from torque.audio.whisper_service import WhisperService


class SpeechService:
    """Microphone + speech recognition."""

    def __init__(self, microphone=None, whisper=None):

        self.microphone = microphone or MicrophoneService()
        self.whisper = whisper or WhisperService()

    def listen(self, timeout=None, flush=False, max_seconds=None):
        """
        Returns the transcript, "" if speech was heard but not recognised,
        or None if nobody spoke before `timeout` / the wait was interrupted.

        flush=True drops audio buffered before this call, such as Torque's
        own voice still echoing in the room.

        max_seconds skips transcription of longer recordings (returns ""):
        used while waiting for the wake word so a long TV monologue is not
        run through Whisper.
        """

        audio = self.microphone.record(timeout=timeout, flush=flush)

        if audio is None:
            return None

        if max_seconds and len(audio) / self.microphone.SAMPLE_RATE > max_seconds:
            return ""

        return self.whisper.transcribe(audio).strip()

    def set_level_callback(self, callback):
        self.microphone.on_level = callback

    def interrupt(self):
        self.microphone.interrupt()

    def stop(self):
        self.microphone.stop()

    def reset(self):
        self.microphone.reset()

    def flush(self):
        self.microphone.flush()

    def close(self):
        logger.info("Closing microphone.")
        self.microphone.close()
