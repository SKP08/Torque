import queue
import threading
import time

import numpy as np
from loguru import logger

from torque.paths import MODELS_DIR
from torque.system.config_service import load_config
from torque.utils.text import split_sentences

BLOCK_SAMPLES = 2048


def _default_stream(sample_rate):
    import sounddevice as sd

    return sd.OutputStream(samplerate=sample_rate, channels=1, dtype="int16")


class TTSService:
    """
    Piper text-to-speech with streaming playback: the reply is synthesised
    one sentence at a time, so the first sentence starts playing while the
    rest is still being generated. stop() interrupts playback quickly.
    """

    def __init__(self, voice=None, stream_factory=None):

        self._stop = threading.Event()
        self._stream_factory = stream_factory or _default_stream

        if voice is None:
            voice = self._load_voice()

        self.voice = voice
        self.sample_rate = voice.config.sample_rate

    @staticmethod
    def _load_voice():

        from piper import PiperVoice

        name = load_config()["piper_voice"]

        model = MODELS_DIR / "piper" / f"{name}.onnx"
        config = MODELS_DIR / "piper" / f"{name}.onnx.json"

        if not model.exists() or not config.exists():
            raise FileNotFoundError(
                f"Piper voice not found at {model}.\n"
                f"Download it with:\n"
                f"  uv run python -m piper.download_voices {name} "
                f"--download-dir models/piper"
            )

        logger.info("Loading Piper...")

        start = time.perf_counter()

        voice = PiperVoice.load(str(model), str(config))

        logger.success(f"Piper ready in {time.perf_counter() - start:.2f}s.")

        return voice

    # ----------------------------------------------------------

    def _synthesize(self, sentence: str):

        chunks = [
            chunk.audio_int16_array for chunk in self.voice.synthesize(sentence)
        ]

        if not chunks:
            return None

        return np.concatenate(chunks)

    def _produce(self, sentences, audio_queue):
        """Synthesis thread: sentence audio -> queue; None marks the end."""

        try:
            for sentence in sentences:

                if self._stop.is_set():
                    break

                audio = self._synthesize(sentence)

                while audio is not None and not self._stop.is_set():
                    try:
                        audio_queue.put(audio, timeout=0.1)
                        break
                    except queue.Full:
                        continue

        except Exception:  # noqa: BLE001
            logger.exception("Speech synthesis failed.")

        finally:
            while True:
                try:
                    audio_queue.put(None, timeout=0.1)
                    break
                except queue.Full:
                    if self._stop.is_set():
                        break

    def speak(self, text: str) -> bool:
        """
        Speak `text`. Returns True if it finished, False if interrupted.
        """

        sentences = split_sentences(text)

        if not sentences:
            return True

        logger.info(f"Speaking: {text}")

        self._stop.clear()

        audio_queue = queue.Queue(maxsize=3)

        producer = threading.Thread(
            target=self._produce,
            args=(sentences, audio_queue),
            name="TorqueTTS",
            daemon=True,
        )

        producer.start()

        with self._stream_factory(self.sample_rate) as stream:

            while True:

                try:
                    audio = audio_queue.get(timeout=0.1)
                except queue.Empty:
                    if self._stop.is_set() and not producer.is_alive():
                        break
                    continue

                if audio is None:
                    break

                for start in range(0, len(audio), BLOCK_SAMPLES):

                    if self._stop.is_set():
                        break

                    block = audio[start:start + BLOCK_SAMPLES]

                    stream.write(block.reshape(-1, 1))

                if self._stop.is_set():
                    break

        interrupted = self._stop.is_set()

        # Wake the producer so it can exit if we stopped early.
        self._stop.set()

        producer.join(timeout=2)

        return not interrupted

    def stop(self):
        """Interrupt speech that is currently playing."""

        self._stop.set()
