"""Voice activity detection without PyTorch.

Silero VAD is run directly on onnxruntime (already installed for
faster-whisper), which keeps `torch` (about 2 GB, slow to import) out of
Torque entirely. If no model can be found an energy-based detector is used
instead, so Torque degrades rather than refusing to start.
"""

import os
from pathlib import Path

import numpy as np
from loguru import logger

from torque.paths import MODELS_DIR

SAMPLE_RATE = 16000
BLOCK_SIZE = 512       # 32 ms at 16 kHz: the only window size Silero accepts
CONTEXT_SIZE = 64      # samples of the previous block fed in front of each block
BLOCK_SECONDS = BLOCK_SIZE / SAMPLE_RATE


def find_model_path() -> Path | None:
    """
    Locate a Silero VAD ONNX file: $TORQUE_VAD_MODEL, then
    models/silero_vad.onnx, then the copy bundled with faster-whisper.
    """

    candidates = []

    env = os.environ.get("TORQUE_VAD_MODEL")

    if env:
        candidates.append(Path(env))

    candidates.append(MODELS_DIR / "silero_vad.onnx")

    try:
        import faster_whisper

        assets = Path(faster_whisper.__file__).parent / "assets"

        # Newest version first (silero_vad_v6.onnx before silero_vad.onnx).
        candidates.extend(sorted(assets.glob("silero_vad*.onnx"), reverse=True))

    except ImportError:
        pass

    for path in candidates:
        if path.is_file():
            return path

    return None


class SileroModel:
    """
    Streaming Silero VAD. Call it with consecutive 512-sample float32
    blocks; it returns the probability (0-1) that the block is speech.

    Handles both ONNX layouts in circulation: the official one
    (inputs input/state/sr) and the sequence export bundled with
    faster-whisper (inputs input/h/c). State is carried between calls.
    """

    def __init__(self, path):

        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.log_severity_level = 4

        self.session = onnxruntime.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
            sess_options=options,
        )

        names = {item.name for item in self.session.get_inputs()}

        if {"state", "sr"} <= names:
            self.layout = "official"
        elif {"h", "c"} <= names:
            self.layout = "sequence"
        else:
            raise RuntimeError(f"Unsupported VAD model inputs: {sorted(names)}")

        self.path = Path(path)

        self.reset()

    def reset(self):

        self._context = np.zeros((1, CONTEXT_SIZE), dtype=np.float32)

        if self.layout == "official":
            self._state = np.zeros((2, 1, 128), dtype=np.float32)
            self._sr = np.array(SAMPLE_RATE, dtype=np.int64)
        else:
            self._h = np.zeros((1, 1, 128), dtype=np.float32)
            self._c = np.zeros((1, 1, 128), dtype=np.float32)

    def __call__(self, block) -> float:

        block = np.asarray(block, dtype=np.float32).reshape(1, -1)

        if block.shape[1] != BLOCK_SIZE:
            raise ValueError(f"VAD blocks must have {BLOCK_SIZE} samples, got {block.shape[1]}")

        x = np.concatenate([self._context, block], axis=1)

        self._context = x[:, -CONTEXT_SIZE:]

        if self.layout == "official":

            out, self._state = self.session.run(
                None,
                {"input": x, "state": self._state, "sr": self._sr},
            )

        else:

            out, self._h, self._c = self.session.run(
                None,
                {"input": x, "h": self._h, "c": self._c},
            )

        return float(np.asarray(out).reshape(-1)[0])


class EnergyModel:
    """Last-resort detector: loudness only. Fine in a quiet room."""

    LOUD = 0.02   # RMS that counts as clearly speech

    def reset(self):
        pass

    def __call__(self, block) -> float:

        block = np.asarray(block, dtype=np.float32)

        rms = float(np.sqrt(np.mean(block * block))) if block.size else 0.0

        return min(1.0, rms / self.LOUD)


def load_model():

    path = find_model_path()

    if path is not None:

        try:
            model = SileroModel(path)

            logger.info(f"Voice activity model: {path.name} ({model.layout})")

            return model

        except Exception:  # noqa: BLE001
            logger.exception(f"Could not load VAD model {path}")

    logger.warning(
        "Silero VAD model not found; using a simple loudness detector instead."
    )

    return EnergyModel()


class VADIterator:
    """
    Turns per-block speech probabilities into "start" / "end" events.

    - "start" after `min_speech_blocks` consecutive blocks above `threshold`
    - "end" after `min_silence` seconds below `neg_threshold`
    - probabilities in between count as speech (hysteresis), so a quiet
      syllable does not end the utterance
    """

    def __init__(
        self,
        model=None,
        threshold=0.5,
        neg_threshold=None,
        min_silence=0.35,
        min_speech_blocks=2,
    ):

        self.model = model if model is not None else load_model()

        self.threshold = threshold
        self.neg_threshold = neg_threshold if neg_threshold is not None else max(0.05, threshold - 0.15)
        self.min_silence_blocks = max(1, round(min_silence / BLOCK_SECONDS))
        self.min_speech_blocks = max(1, min_speech_blocks)

        self.reset()

    def reset(self):

        self.model.reset()

        self.triggered = False
        self._speech_run = 0
        self._silence_run = 0

    def process(self, block) -> str | None:
        """Feed one 512-sample block. Returns "start", "end" or None."""

        probability = self.model(block)

        if not self.triggered:

            self._speech_run = self._speech_run + 1 if probability >= self.threshold else 0

            if self._speech_run >= self.min_speech_blocks:
                self.triggered = True
                self._silence_run = 0
                return "start"

            return None

        if probability < self.neg_threshold:

            self._silence_run += 1

            if self._silence_run >= self.min_silence_blocks:
                self.triggered = False
                self._speech_run = 0
                return "end"

        else:
            self._silence_run = 0

        return None
