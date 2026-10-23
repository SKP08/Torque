"""
Kokoro-82M text-to-speech on onnxruntime.

Written against the model directly (rather than the kokoro-onnx package,
which doesn't support Python 3.14). Model: Kokoro-82M by hexgrad, Apache-2.0;
ONNX export from the kokoro-onnx project (MIT). The phoneme vocabulary in
kokoro_vocab.json is the model's own (Apache-2.0).

Pipeline per sentence:  text -> espeak phonemes -> token ids ->
                        onnx (tokens + voice style + speed) -> 24 kHz audio
"""

import json
import threading
from pathlib import Path

import numpy as np
from loguru import logger

SAMPLE_RATE = 24000
MAX_PHONEMES = 510                    # the model's context
VOCAB_PATH = Path(__file__).with_name("kokoro_vocab.json")

# espeak keeps process-wide state, so phonemizing is serialised.
_espeak_lock = threading.Lock()

_NUMPY_TYPES = {
    "tensor(float)": np.float32,
    "tensor(float16)": np.float16,
    "tensor(double)": np.float64,
    "tensor(int32)": np.int32,
    "tensor(int64)": np.int64,
}


def load_vocab() -> dict:

    with open(VOCAB_PATH, encoding="utf-8") as file:
        return json.load(file)


def espeak_phonemizer(language: str):
    """Text -> IPA phonemes using the espeak-ng that ships with espeakng-loader."""

    import espeakng_loader
    import phonemizer
    from phonemizer.backend.espeak.wrapper import EspeakWrapper

    with _espeak_lock:
        EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
        EspeakWrapper.set_library(espeakng_loader.get_library_path())

    def phonemize(text: str) -> str:

        with _espeak_lock:
            return phonemizer.phonemize(
                text, language, preserve_punctuation=True, with_stress=True
            )

    return phonemize


def split_phonemes(phonemes: str, limit: int = MAX_PHONEMES) -> list[str]:
    """Cut at the least disruptive place (sentence, clause, word) to fit the model."""

    if len(phonemes) <= limit:
        return [phonemes] if phonemes else []

    for marks in (".!?", ",;:", " "):

        cut = max(phonemes.rfind(m, 0, limit) for m in marks)

        if cut > limit // 3:
            head, tail = phonemes[: cut + 1].strip(), phonemes[cut + 1:].strip()
            return ([head] if head else []) + split_phonemes(tail, limit)

    return [phonemes[:limit]] + split_phonemes(phonemes[limit:], limit)


def trim_silence(audio: np.ndarray, threshold: float = 0.004, keep: int = 600) -> np.ndarray:
    """Remove the model's leading/trailing silence (keeping a few ms)."""

    loud = np.flatnonzero(np.abs(audio) > threshold)

    if loud.size == 0:
        return audio[:0]

    return audio[max(0, loud[0] - keep): loud[-1] + keep]


class KokoroEngine:
    """text -> int16 audio. Same interface as PiperEngine."""

    sample_rate = SAMPLE_RATE

    def __init__(self, session, voices, voice="bm_george", speed=1.0,
                 language="en-gb", phonemize=None, vocab=None, pause_seconds=0.14):

        if voice not in voices:
            raise ValueError(f"Voice '{voice}' not found. Available: {', '.join(sorted(voices))[:200]}")

        if not 0.5 <= speed <= 2.0:
            raise ValueError("tts_speed must be between 0.5 and 2.0")

        self.session = session
        self.style = np.asarray(voices[voice], dtype=np.float32)
        self.speed = speed
        self.vocab = vocab or load_vocab()
        self.phonemize = phonemize or espeak_phonemizer(language)
        self.pause = np.zeros(int(pause_seconds * SAMPLE_RATE), dtype=np.int16)

        inputs = {i.name: _NUMPY_TYPES.get(i.type, np.float32) for i in session.get_inputs()}

        self._tokens_name = "input_ids" if "input_ids" in inputs else "tokens"
        self._dtypes = inputs

    @classmethod
    def load(cls, model_path, voices_path, voice="bm_george", speed=1.0, language="en-gb"):

        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 0          # all cores; synthesis is bursty

        session = onnxruntime.InferenceSession(
            str(model_path), sess_options=options, providers=["CPUExecutionProvider"]
        )

        voices = np.load(str(voices_path))

        return cls(session, voices, voice=voice, speed=speed, language=language)

    # ----------------------------------------------------------

    def _tokens(self, phonemes: str) -> list[int]:
        return [i for i in map(self.vocab.get, phonemes) if i is not None]

    def _infer(self, tokens: list[int]) -> np.ndarray:

        style = self.style[min(len(tokens), len(self.style)) - 1]

        feed = {
            self._tokens_name: np.array([[0, *tokens, 0]], dtype=self._dtypes[self._tokens_name]),
            "style": np.asarray(style, dtype=self._dtypes["style"]),
            "speed": np.array([self.speed], dtype=self._dtypes["speed"]),
        }

        return np.asarray(self.session.run(None, feed)[0]).ravel()

    def synthesize(self, text: str):
        """int16 audio for one sentence (or None if nothing is speakable)."""

        text = " ".join(text.split())

        if not text:
            return None

        phonemes = " ".join(self.phonemize(text).split())

        parts = []

        for batch in split_phonemes(phonemes):

            tokens = self._tokens(batch)

            if not tokens:
                continue

            audio = trim_silence(self._infer(tokens))

            if audio.size:
                parts.append(np.clip(audio, -1.0, 1.0))
                parts.append(np.zeros(int(0.06 * SAMPLE_RATE), dtype=np.float32))

        if not parts:
            return None

        samples = np.concatenate(parts[:-1])

        return np.concatenate([(samples * 32767).astype(np.int16), self.pause])


class PiperEngine:
    """The existing Piper voice behind the same interface."""

    def __init__(self, voice):

        self.voice = voice
        self.sample_rate = voice.config.sample_rate

    def synthesize(self, text: str):

        chunks = [chunk.audio_int16_array for chunk in self.voice.synthesize(text)]

        return np.concatenate(chunks) if chunks else None
