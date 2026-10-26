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


# Kokoro must synthesise faster than this multiple of real time to be usable;
# otherwise there would be gaps between sentences and Piper is used instead.
MAX_USABLE_RTF = 0.85
BENCHMARK_SENTENCE = "The quick brown fox jumps over the lazy dog, and then it runs away."


def measure_rtf(engine, runs=2) -> float:
    """Seconds of compute per second of audio (lower is faster). Warms up first."""

    engine.synthesize("Warm up.")

    best = None

    for _ in range(runs):

        start = time.perf_counter()
        audio = engine.synthesize(BENCHMARK_SENTENCE)
        elapsed = time.perf_counter() - start

        if audio is None or not len(audio):
            return float("inf")

        rtf = elapsed / (len(audio) / engine.sample_rate)

        best = rtf if best is None else min(best, rtf)

    return best


def load_engine(config=None, kokoro_factory=None, piper_factory=None, rtf_probe=measure_rtf):
    """
    Pick the voice: Kokoro (natural) when it is installed AND fast enough on
    this PC, otherwise Piper. `tts_engine` can force either.
    """

    config = config or load_config()

    choice = config["tts_engine"]

    kokoro_dir = MODELS_DIR / "kokoro"
    model = kokoro_dir / config["kokoro_model"]
    voices = kokoro_dir / "voices-v1.0.bin"

    if choice in ("auto", "kokoro"):

        if model.exists() and voices.exists():

            try:
                factory = kokoro_factory or _load_kokoro
                engine = factory(model, voices, config)

                rtf = rtf_probe(engine) if choice == "auto" else None

                if rtf is None or rtf <= MAX_USABLE_RTF:
                    logger.success(
                        "Voice: Kokoro" + (f" (speed {rtf:.2f}x real time)" if rtf else "")
                    )
                    return engine

                logger.warning(
                    f"Kokoro runs at {rtf:.2f}x real time on this PC (too slow); using Piper. "
                    f"Set tts_engine to 'kokoro' to force it."
                )

            except Exception:  # noqa: BLE001
                logger.warning("Kokoro could not start; using Piper.", exc_info=True)

        elif choice == "kokoro":
            raise FileNotFoundError(
                "Kokoro files not found. Run: uv run python -m torque.audio.voice_download"
            )

        else:
            logger.info("Kokoro voice not installed; using Piper. (uv run python -m torque.audio.voice_download)")

    from torque.audio.kokoro_engine import PiperEngine

    return PiperEngine((piper_factory or TTSService._load_voice)())


def _load_kokoro(model, voices, config):

    from torque.audio.kokoro_engine import KokoroEngine

    return KokoroEngine.load(
        model, voices, voice=config["kokoro_voice"], speed=config["tts_speed"],
        language=config["kokoro_language"],
    )


class TTSService:
    """
    Text-to-speech with streaming playback: the reply is synthesised one
    sentence at a time, so the first sentence starts playing while the rest
    is still being generated. stop() interrupts playback quickly.

    The voice is an "engine" (Kokoro or Piper): anything with sample_rate and
    synthesize(sentence) -> int16 array.
    """

    def __init__(self, voice=None, stream_factory=None, engine=None):

        self._stop = threading.Event()
        self.tap = None                 # tap(block, sample_rate): what is about to be played (for barge-in)
        self._stream_factory = stream_factory or _default_stream

        if engine is None:

            if voice is not None:                  # a raw Piper voice (tests, old callers)
                from torque.audio.kokoro_engine import PiperEngine

                engine = PiperEngine(voice)
            else:
                engine = load_engine()

        self.engine = engine
        self.voice = getattr(engine, "voice", None)
        self.sample_rate = engine.sample_rate

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

        return self.engine.synthesize(sentence)

    def warm_up(self):
        """Run one throw-away synthesis so the first real reply is quick."""

        try:
            self._synthesize("Ready.")
        except Exception:  # noqa: BLE001
            logger.debug("TTS warm-up failed.", exc_info=True)

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
            close = getattr(sentences, "close", None)

            if close:
                try:
                    close()          # stops an LLM stream that is still generating
                except Exception:  # noqa: BLE001
                    logger.debug("Could not close sentence source.", exc_info=True)

            while True:
                try:
                    audio_queue.put(None, timeout=0.1)
                    break
                except queue.Full:
                    if self._stop.is_set():
                        break

    def speak(self, text) -> bool:
        """
        Speak `text` - a string, or any iterable of sentences (such as a
        generator that is still producing them, so speech can begin before
        the whole reply exists). Returns True if it finished, False if
        interrupted.
        """

        if isinstance(text, str):

            sentences = split_sentences(text)

            if not sentences:
                return True

            logger.debug(f"Speaking: {text}")

        else:
            sentences = text

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

                    if self.tap:
                        try:
                            self.tap(block, self.sample_rate)
                        except Exception:  # noqa: BLE001
                            logger.debug("Playback tap failed.", exc_info=True)

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
