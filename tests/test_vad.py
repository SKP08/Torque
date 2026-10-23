import wave
from pathlib import Path

import numpy as np
import pytest

from torque.audio.vad import (
    BLOCK_SIZE,
    EnergyModel,
    SileroModel,
    VADIterator,
    find_model_path,
    load_model,
)

SAMPLE = Path(__file__).parent / "data" / "speech_sample.wav"


class Scripted:
    """Fake model that returns a scripted sequence of probabilities."""

    def __init__(self, probs):
        self.probs = list(probs)
        self.resets = 0

    def reset(self):
        self.resets += 1

    def __call__(self, block):
        return self.probs.pop(0)


def run(iterator, count):
    block = np.zeros(BLOCK_SIZE, dtype=np.float32)
    return [iterator.process(block) for _ in range(count)]


def test_start_needs_consecutive_speech_blocks():
    it = VADIterator(Scripted([0.9, 0.1, 0.9, 0.9]), min_speech_blocks=2)
    assert run(it, 4) == [None, None, None, "start"]


def test_end_after_min_silence_only():
    it = VADIterator(Scripted([0.9] * 2 + [0.1] * 3 + [0.9] + [0.1] * 4), min_silence=4 * 0.032, min_speech_blocks=1)
    events = run(it, 10)
    # 3 quiet blocks are not enough; speech resumes; 4 quiet blocks end it.
    assert events.count("start") == 1 and events.count("end") == 1
    assert events[-1] == "end"


def test_hysteresis_keeps_quiet_syllables_in_the_utterance():
    # 0.4 is below the start threshold (0.5) but above the end threshold (0.35).
    it = VADIterator(Scripted([0.9, 0.9] + [0.4] * 30), min_silence=0.1)
    events = run(it, 32)
    assert events == [None, "start"] + [None] * 30


def test_reset_clears_state_and_model():
    model = Scripted([0.9, 0.9, 0.9])
    it = VADIterator(model, min_speech_blocks=1)
    run(it, 1)
    assert it.triggered
    it.reset()
    assert not it.triggered and model.resets == 2   # once in __init__, once here


def test_energy_model_fallback():
    model = EnergyModel()
    assert model(np.zeros(BLOCK_SIZE, np.float32)) == 0.0
    assert model(np.full(BLOCK_SIZE, 0.3, np.float32)) == 1.0


def test_load_model_never_returns_none():
    assert hasattr(load_model(), "reset")


# ---- real model --------------------------------------------------------

needs_model = pytest.mark.skipif(find_model_path() is None, reason="no Silero ONNX model installed")


def read_sample():
    with wave.open(str(SAMPLE)) as f:
        assert f.getframerate() == 16000 and f.getnchannels() == 1
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def events_for(signal, **kwargs):
    it = VADIterator(SileroModel(find_model_path()), **kwargs)
    blocks = signal[: len(signal) // BLOCK_SIZE * BLOCK_SIZE].reshape(-1, BLOCK_SIZE)
    return [(i, e) for i, e in ((i, it.process(b)) for i, b in enumerate(blocks)) if e]


@needs_model
def test_real_model_ignores_silence_and_noise():
    rng = np.random.default_rng(1)
    for signal in (
        np.zeros(BLOCK_SIZE * 100, np.float32),
        rng.normal(0, 0.05, BLOCK_SIZE * 100).astype(np.float32),
        (0.3 * np.sin(2 * np.pi * 440 * np.arange(BLOCK_SIZE * 100) / 16000)).astype(np.float32),
    ):
        assert events_for(signal) == []


@needs_model
def test_real_model_finds_the_two_phrases_in_real_speech():
    speech = read_sample()
    padded = np.concatenate([np.zeros(16000, np.float32), speech, np.zeros(16000, np.float32)])

    events = events_for(padded, min_silence=0.35)

    assert [e for _, e in events] == ["start", "end", "start", "end"]

    seconds = [i * BLOCK_SIZE / 16000 for i, _ in events]

    assert 0.9 < seconds[0] < 1.5           # first phrase starts ~1 s in (after the padding)
    assert seconds[2] - seconds[1] < 1.5    # the natural pause between phrases
    assert seconds[3] > 5.0                 # second phrase ends after ~5.7 s


@needs_model
def test_real_model_with_long_silence_threshold_merges_phrases():
    speech = read_sample()
    padded = np.concatenate([np.zeros(16000, np.float32), speech, np.zeros(32000, np.float32)])

    events = events_for(padded, min_silence=1.0)

    assert [e for _, e in events] == ["start", "end"]


@needs_model
def test_real_model_is_fast_enough_for_realtime():
    import time

    model = SileroModel(find_model_path())
    block = np.zeros(BLOCK_SIZE, np.float32)

    start = time.perf_counter()
    for _ in range(300):
        model(block)

    per_block_ms = (time.perf_counter() - start) / 300 * 1000

    assert per_block_ms < 8   # a block is 32 ms of audio
