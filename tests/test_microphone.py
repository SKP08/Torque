import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from torque.audio.microphone import MicrophoneService
from torque.audio.utterance import UtteranceCollector
from torque.audio.vad import BLOCK_SIZE, SileroModel, VADIterator, find_model_path

SAMPLE = Path(__file__).parent / "data" / "speech_sample.wav"


def speech_int16():
    with wave.open(str(SAMPLE)) as f:
        return np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)


class FakeStream:
    """Feeds scripted int16 audio into the callback from a thread."""

    def __init__(self, callback, audio, chunk=800, realtime=False, loop_silence=True):
        self.callback = callback
        self.audio = audio
        self.chunk = chunk
        self.realtime = realtime
        self.loop_silence = loop_silence
        self.active = False
        self._thread = None
        self.closed = False

    def start(self):
        self.active = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        position = 0
        while self.active:
            piece = self.audio[position:position + self.chunk]
            position += self.chunk
            if piece.size == 0:
                if not self.loop_silence:
                    time.sleep(0.01)
                    continue
                piece = np.zeros(self.chunk, dtype=np.int16)
            self.callback(piece.tobytes(), len(piece), None, None)
            time.sleep(0.0 if not self.realtime else len(piece) / 16000)

    def stop(self):
        self.active = False

    def close(self):
        self.closed = True


def make_mic(audio, **kw):
    holder = {}

    def factory(callback):
        holder["stream"] = FakeStream(callback, audio, **kw)
        return holder["stream"]

    vad = VADIterator(SileroModel(find_model_path()), min_silence=0.3)
    mic = MicrophoneService(vad=vad, end_silence=0.9, short_end_silence=0.5, stream_factory=factory)
    return mic, holder


needs_model = pytest.mark.skipif(find_model_path() is None, reason="no VAD model")


@needs_model
def test_record_captures_the_phrases_with_preroll():
    silence = np.zeros(16000, dtype=np.int16)
    mic, _ = make_mic(np.concatenate([silence, speech_int16(), silence, silence]))
    audio = mic.record(timeout=5)
    mic.close()

    assert audio is not None and audio.dtype == np.float32
    # ~4.9 s of speech + pre-roll + grace
    assert 4.5 < len(audio) / 16000 < 7.5
    # Quiet pre-roll then speech: the loudest part is well inside the clip.
    assert np.abs(audio).max() > 0.1


@needs_model
def test_pause_inside_grace_keeps_one_utterance():
    # Phrase 1 and 2 are ~0.7 s apart in the sample. This is a longer
    # utterance, so the 0.9 s end-of-speech wait applies and they stay together.
    silence = np.zeros(16000, dtype=np.int16)
    mic, _ = make_mic(np.concatenate([silence, speech_int16(), silence, silence]))
    audio = mic.record(timeout=5)
    mic.close()
    assert len(audio) / 16000 > 4.5


@needs_model
def test_timeout_with_only_silence():
    mic, _ = make_mic(np.zeros(16000 * 3, dtype=np.int16), realtime=False)
    start = time.monotonic()
    assert mic.record(timeout=0.5) is None
    assert time.monotonic() - start < 2
    mic.close()


@needs_model
def test_interrupt_is_one_shot_and_cancel_is_sticky():
    mic, _ = make_mic(np.zeros(16000 * 3, dtype=np.int16))

    threading.Timer(0.2, mic.interrupt).start()
    assert mic.record() is None          # interrupted

    assert mic.record(timeout=0.3) is None   # ran to its own timeout, not interrupted again

    mic.stop()
    assert mic.record() is None          # cancelled immediately
    assert mic.record() is None          # ...and stays cancelled

    mic.reset()
    assert mic.record(timeout=0.3) is None   # works again (times out normally)
    mic.close()


@needs_model
def test_stream_is_opened_once_and_reused():
    opened = []

    def factory(callback):
        stream = FakeStream(callback, np.zeros(16000, dtype=np.int16))
        opened.append(stream)
        return stream

    mic = MicrophoneService(
        vad=VADIterator(SileroModel(find_model_path())), end_silence=0.9, short_end_silence=0.5, stream_factory=factory
    )
    mic.record(timeout=0.2)
    mic.record(timeout=0.2)
    mic.record(timeout=0.2)
    assert len(opened) == 1
    mic.close()
    assert opened[0].closed


@needs_model
def test_odd_sized_callbacks_are_resliced_into_exact_blocks():
    seen = []

    class Recording(VADIterator):
        def process(self, block):
            seen.append(len(block))
            return None

    mic = MicrophoneService(
        vad=Recording(SileroModel(find_model_path())),
        end_silence=0.9, short_end_silence=0.5,
        stream_factory=lambda cb: FakeStream(cb, np.zeros(16000, dtype=np.int16), chunk=333),
    )
    mic.record(timeout=0.3)
    mic.close()
    assert seen and set(seen) == {BLOCK_SIZE}


@needs_model
def test_level_callback_and_flush():
    levels = []
    mic, _ = make_mic(speech_int16())
    mic.on_level = levels.append
    mic.record(timeout=1)
    mic.close()
    assert levels and max(levels) > 0.01

    mic.flush()
    assert mic._queue.empty()


def test_stalled_stream_is_reopened():
    opened = []

    def factory(callback):
        silent = len(opened) == 0       # first stream never delivers audio
        stream = FakeStream(callback, np.zeros(0 if silent else 16000, dtype=np.int16), loop_silence=not silent)
        opened.append(stream)
        return stream

    import torque.audio.microphone as module

    original = module.STALL_SECONDS
    module.STALL_SECONDS = 0.3
    try:
        mic = MicrophoneService(vad=VADIterator(model=type("M", (), {"reset": lambda s: None, "__call__": lambda s, b: 0.0})()),
                                end_silence=0.9, short_end_silence=0.5, stream_factory=factory)
        mic.record(timeout=1.5)
        mic.close()
    finally:
        module.STALL_SECONDS = original

    assert len(opened) >= 2


# ---- collector (audio-time grace) -------------------------------------

def block(value=0.1):
    return np.full(512, value, dtype=np.float32)


def test_collector_grace_is_measured_in_audio_time_not_wall_time():
    # All blocks arrive instantly (wall clock never advances) yet the grace
    # period still ends after enough AUDIO has gone by.
    c = UtteranceCollector(grace_seconds=0.3, clock=lambda: 0.0)
    c.feed(block(), "start")
    c.feed(block(), "end")
    done = False
    for _ in range(9):               # 9 * 32 ms = 288 ms < 300 ms
        done = c.feed(block(), None)
    assert done is False
    assert c.feed(block(), None) is True


def test_collector_waits_less_after_a_short_utterance():
    def run(speech_blocks):
        c = UtteranceCollector(grace_seconds=0.6, short_grace_seconds=0.2,
                               short_utterance_seconds=1.0, clock=lambda: 0.0)
        c.feed(block(), "start")
        for _ in range(speech_blocks):
            c.feed(block(), None)
        c.feed(block(), "end")
        n = 0
        while not c.feed(block(), None):
            n += 1
        return (n + 1) * 512 / 16000

    short = run(10)       # ~0.35 s of audio
    long = run(60)        # ~1.9 s of audio
    assert 0.2 <= short < 0.3
    assert 0.6 <= long < 0.7


def test_collector_wall_clock_safety_net_when_blocks_stop():
    class Clock:
        t = 0.0
        def __call__(self): return self.t
    clock = Clock()
    c = UtteranceCollector(grace_seconds=0.3, clock=clock)
    c.feed(block(), "start")
    c.feed(block(), "end")
    assert not c.expired()
    clock.t = 1.0
    assert c.expired()


def test_collector_preroll_and_continuation():
    c = UtteranceCollector(preroll_seconds=0.1, grace_seconds=1.0, clock=lambda: 0.0)   # 3 pre-roll blocks
    for i in range(10):
        c.feed(block(i), None)
    c.feed(block(99), "start")
    assert len(c.audio()) == 3 * 512 and c.audio()[0] == 8

    c.feed(block(2), "end")
    c.feed(block(0), None)         # pause
    c.feed(block(3), "start")      # continues within grace
    assert c.state == c.SPEAKING
    assert list(c.audio()[::512])[-3:] == [2, 0, 3]


def test_collector_max_length_and_empty():
    c = UtteranceCollector(max_seconds=0.1)
    c.feed(block(), "start")
    assert any(c.feed(block(), None) for _ in range(10))
    assert UtteranceCollector().audio() is None
