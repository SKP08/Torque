import threading
import time
from queue import Empty, Full, Queue

import numpy as np
from loguru import logger

from torque.audio.utterance import UtteranceCollector
from torque.audio.vad import BLOCK_SIZE, SAMPLE_RATE, VADIterator
from torque.system.config_service import load_config

# If no audio arrives for this long the device probably vanished
# (headset unplugged, driver reset): reopen the stream.
STALL_SECONDS = 2.0


def _default_stream_factory(callback):

    import sounddevice as sd

    return sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK_SIZE,
        channels=1,
        dtype="int16",
        callback=callback,
    )


class MicrophoneService:
    """
    Keeps ONE microphone stream open and cuts it into utterances with VAD.

    Staying open matters: opening a stream per utterance costs latency,
    drops the first syllable, and makes always-on wake-word listening
    impossible. Audio stays in memory; nothing is written to disk.

    Control:
        interrupt()  make the current record() return None once
        stop()       cancel and keep cancelling until reset()
        reset()      new conversation: clear cancel, drop stale audio
        flush()      drop buffered audio (e.g. Torque's own voice)
    """

    SAMPLE_RATE = SAMPLE_RATE
    BLOCK_SIZE = BLOCK_SIZE

    # The VAD itself reports "speech ended" after this much silence; the
    # collector then waits a little longer (see UtteranceCollector).
    VAD_SILENCE = 0.3

    def __init__(self, vad=None, end_silence=None, short_end_silence=None, stream_factory=None):
        """
        end_silence        total silence that ends a longer utterance
        short_end_silence  total silence that ends a short one (commands)
        """

        logger.info("Initializing Microphone...")

        config = load_config()

        if end_silence is None:
            end_silence = float(config["end_of_speech_silence"])

        if short_end_silence is None:
            short_end_silence = float(config["end_of_speech_silence_short"])

        short_end_silence = min(short_end_silence, end_silence)

        self._grace = max(0.1, end_silence - self.VAD_SILENCE)
        self._short_grace = max(0.0, short_end_silence - self.VAD_SILENCE)

        self.vad = vad or VADIterator(min_silence=self.VAD_SILENCE)

        self._stream_factory = stream_factory or _default_stream_factory

        self._queue = Queue(maxsize=1500)    # about 48 s of audio
        self._carry = np.zeros(0, dtype=np.int16)
        self._stream = None
        self._lock = threading.Lock()
        self._last_block = time.monotonic()

        self._cancel = threading.Event()
        self._interrupt = threading.Event()

        self.on_level = None

        logger.success("Microphone ready.")

    # ----------------------------------------------------------
    # STREAM
    # ----------------------------------------------------------

    def _callback(self, indata, frames, time_info, status):
        """PortAudio thread: slice into exact 512-sample blocks and queue."""

        if status:
            logger.debug(f"Audio status: {status}")

        samples = np.frombuffer(indata, dtype=np.int16)

        if self._carry.size:
            samples = np.concatenate([self._carry, samples])

        usable = samples.size // BLOCK_SIZE * BLOCK_SIZE

        self._carry = samples[usable:].copy()

        for block in samples[:usable].reshape(-1, BLOCK_SIZE):

            try:
                self._queue.put_nowait(block.copy())

            except Full:
                # Nobody is reading; keep the newest audio.
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(block.copy())
                except (Empty, Full):
                    pass

        self._last_block = time.monotonic()

    def start(self):
        """Open the stream if it is not already running."""

        with self._lock:

            if self._stream is not None and getattr(self._stream, "active", False):
                return

            self._close_locked()

            self._carry = np.zeros(0, dtype=np.int16)
            self._last_block = time.monotonic()

            stream = self._stream_factory(self._callback)
            stream.start()

            self._stream = stream

            logger.info("Microphone stream started.")

    def _close_locked(self):

        stream, self._stream = self._stream, None

        if stream is None:
            return

        try:
            stream.stop()
            stream.close()
        except Exception:  # noqa: BLE001
            logger.debug("Error closing microphone stream.", exc_info=True)

    def close(self):

        with self._lock:
            self._close_locked()

    # ----------------------------------------------------------
    # CONTROL
    # ----------------------------------------------------------

    def interrupt(self):
        """Make a record() in progress (or the next one) return None, once."""

        self._interrupt.set()

    def stop(self):
        """Cancel recording until reset()."""

        self._cancel.set()

        logger.info("Microphone stopped.")

    def flush(self):
        """Drop everything buffered so far."""

        try:
            while True:
                self._queue.get_nowait()
        except Empty:
            pass

        self._carry = np.zeros(0, dtype=np.int16)

    def reset(self):
        """Prepare for a new conversation."""

        self._cancel.clear()
        self._interrupt.clear()

        self.flush()

        self.vad.reset()

    # ----------------------------------------------------------
    # RECORD
    # ----------------------------------------------------------

    def record(self, timeout=None, flush=False):
        """
        Wait for one utterance. Returns float32 16 kHz mono audio, or None
        if nobody spoke within `timeout` seconds, or if interrupted or
        cancelled.
        """

        self.start()

        if flush:
            self.flush()

        self.vad.reset()

        collector = UtteranceCollector(
            sample_rate=SAMPLE_RATE,
            block_size=BLOCK_SIZE,
            grace_seconds=self._grace,
            short_grace_seconds=self._short_grace,
        )

        started = time.monotonic()

        while True:

            if self._cancel.is_set():
                return None

            if self._interrupt.is_set():
                self._interrupt.clear()
                return None

            if timeout and collector.waiting and time.monotonic() - started > timeout:
                logger.info("No speech before timeout.")
                return None

            try:
                raw = self._queue.get(timeout=0.1)

            except Empty:

                if collector.expired():
                    break

                if time.monotonic() - self._last_block > STALL_SECONDS:
                    self._restart_stream()

                continue

            block = raw.astype(np.float32) / 32768.0

            if self.on_level:
                self.on_level(float(np.sqrt(np.mean(block * block))))

            if collector.feed(block, self.vad.process(block)):
                break

        logger.debug(f"Captured {collector.duration:.1f}s of audio.")

        return collector.audio()

    def _restart_stream(self):

        logger.warning("No audio from the microphone; reopening it.")

        self._last_block = time.monotonic()

        try:
            with self._lock:
                self._close_locked()

            self.start()

        except Exception:  # noqa: BLE001
            logger.exception("Could not reopen the microphone.")
