import threading
import time
from queue import Empty, Queue

import numpy as np
from loguru import logger

from torque.audio.utterance import UtteranceCollector
from torque.audio.vad_service import VADService


class MicrophoneService:
    """
    Records one utterance from the default microphone, using Silero VAD to
    find where speech starts and ends. Audio stays in memory; nothing is
    written to disk.
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    BLOCK_SIZE = 512

    # How long Torque waits after speech ends to see whether the user
    # continues the same thought.
    END_GRACE_SECONDS = 1.0

    def __init__(self):

        logger.info("Initializing Microphone...")

        self.vad = VADService()

        self._cancel = threading.Event()

        logger.success("Microphone ready.")

    @staticmethod
    def _event(result):

        if not result:
            return None

        if "start" in result:
            return "start"

        if "end" in result:
            return "end"

        return None

    def record(self, timeout=None):
        """
        Returns float32 16 kHz mono audio, or None if nobody spoke within
        `timeout` seconds or the recording was cancelled.
        """

        import sounddevice as sd

        logger.info("Waiting for speech...")

        self.vad.reset()

        audio_queue = Queue()

        collector = UtteranceCollector(
            sample_rate=self.SAMPLE_RATE,
            block_size=self.BLOCK_SIZE,
            grace_seconds=self.END_GRACE_SECONDS,
        )

        def callback(indata, frames, time_info, status):

            if status:
                logger.warning(status)

            audio_queue.put(bytes(indata))

        started = time.monotonic()

        with sd.RawInputStream(
            samplerate=self.SAMPLE_RATE,
            blocksize=self.BLOCK_SIZE,
            channels=self.CHANNELS,
            dtype="int16",
            callback=callback,
        ):

            while True:

                if self._cancel.is_set():
                    logger.info("Recording cancelled.")
                    return None

                if (
                    timeout
                    and collector.waiting
                    and time.monotonic() - started > timeout
                ):
                    logger.info("No speech before timeout.")
                    return None

                try:
                    chunk = audio_queue.get(timeout=0.1)

                except Empty:

                    if collector.expired():
                        break

                    continue

                block = (
                    np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                )

                event = self._event(self.vad.process(block))

                if event == "start" and collector.waiting:
                    logger.success("Speech detected.")

                if collector.feed(block, event):
                    break

        logger.success(f"Captured {collector.duration:.1f}s of audio.")

        return collector.audio()

    def stop(self):
        """Abort any recording in progress."""

        self._cancel.set()

        logger.info("Microphone stopped.")

    def reset(self):
        """Prepare for a new conversation."""

        self._cancel.clear()

        self.vad.reset()
