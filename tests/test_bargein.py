import wave
from pathlib import Path

import numpy as np
import pytest

from torque.audio.bargein import BargeIn, to_16k
from torque.audio.echo import EchoCanceller
from torque.audio.vad import BLOCK_SIZE, SAMPLE_RATE, find_model_path, load_model

SAMPLE = Path(__file__).parent / "data" / "speech_sample.wav"
B = BLOCK_SIZE


def speech():
    with wave.open(str(SAMPLE)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64) / 32768


def rms(a):
    return float(np.sqrt(np.mean(np.square(a))))


def room(ref, seed=1, delay=960, length=1500, gain=0.5):
    rng = np.random.default_rng(seed)
    h = np.zeros(length + delay)
    h[delay:] = rng.standard_normal(length) * np.exp(-np.arange(length) / 350) * 0.12
    h[delay] += gain
    return np.convolve(ref, h)[:len(ref)], rng


def torque_voice(seconds):
    return np.tile(speech(), int(seconds / 4.9) + 2)[:SAMPLE_RATE * seconds]


def user_voice(seconds):
    """Different from Torque's: resampled 1.18x faster (higher pitch), still real speech."""
    x = speech()
    y = np.interp(np.arange(0, len(x) - 1, 1.18), np.arange(len(x)), x)
    return np.tile(y, int(seconds / 4) + 2)[:SAMPLE_RATE * seconds]


def to_int16(x):
    return np.clip(x * 32768, -32768, 32767).astype(np.int16)


# ------------------------------------------------------------------ echo canceller

def test_echo_is_cancelled_by_20_db_once_trained():
    ref = torque_voice(15)
    mic, rng = room(ref)
    mic = mic + rng.standard_normal(len(ref)) * 1e-4
    aec = EchoCanceller()
    out = np.concatenate([aec.process(mic[i:i + B], ref[i:i + B]) for i in range(0, len(ref) - B, B)])
    erle = 20 * np.log10(rms(mic[6 * SAMPLE_RATE:]) / rms(out[6 * SAMPLE_RATE:]))
    print(f"\nERLE after 6 s: {erle:.1f} dB")
    assert erle > 18 and aec.converged


def test_silent_reference_does_not_disturb_the_filter():
    aec = EchoCanceller()
    quiet = np.zeros(B)
    for _ in range(50):
        out = aec.process(np.full(B, 0.01), quiet)
    assert np.allclose(out, 0.01) and not aec.converged and np.isfinite(aec._weights).all()


def test_a_different_room_is_learned_after_reset():
    ref = torque_voice(10)
    for seed, delay in ((1, 400), (2, 1400)):
        mic, _ = room(ref, seed=seed, delay=delay)
        aec = EchoCanceller()
        out = np.concatenate([aec.process(mic[i:i + B], ref[i:i + B]) for i in range(0, len(ref) - B, B)])
        assert 20 * np.log10(rms(mic[5 * SAMPLE_RATE:]) / rms(out[5 * SAMPLE_RATE:])) > 15


# ------------------------------------------------------------------ resampling

def test_resample_lengths_and_scaling():
    block = np.ones(2048, dtype=np.int16) * 16384
    out = to_16k(block, 24000)
    assert abs(len(out) - 2048 * 16000 / 24000) <= 1 and abs(out.mean() - 0.5) < 1e-3
    assert len(to_16k(block, 22050)) == round(2048 * 16000 / 22050)
    assert to_16k(np.zeros(0), 24000).size == 0
    assert np.allclose(to_16k(np.full(100, 0.25, dtype=np.float32), 16000), 0.25)


# ------------------------------------------------------------------ detector

pytestmark_model = pytest.mark.skipif(find_model_path() is None, reason="Silero model not found")


def run(ref, mic, barge, start=0):
    """Plays ref through the room into the mic and returns the block index where barge-in fired (or None)."""

    fired = []
    barge.arm(lambda: fired.append(True))
    mic16 = to_int16(mic)

    for index, i in enumerate(range(0, len(ref) - B, B)):
        barge.tap(to_int16(ref[i:i + B]), SAMPLE_RATE)
        if barge.feed(mic16[i:i + B]) and index >= start:
            return index
    return None


@pytestmark_model
def test_torques_own_voice_never_triggers_barge_in():
    ref = torque_voice(25)
    mic, rng = room(ref)
    mic = mic + rng.standard_normal(len(ref)) * 3e-4
    assert run(ref, mic, BargeIn(load_model())) is None


@pytestmark_model
def test_the_user_talking_over_torque_triggers_it_quickly():
    ref = torque_voice(20)
    echo, rng = room(ref)
    mic = echo + rng.standard_normal(len(ref)) * 3e-4
    onset = 12 * SAMPLE_RATE
    user = user_voice(8)
    mic[onset:onset + len(user)] += user[: len(mic) - onset]

    barge = BargeIn(load_model())
    index = run(ref, mic, barge)
    assert index is not None
    delay = (index * B - onset) / SAMPLE_RATE
    print(f"\nbarge-in fired {delay * 1000:.0f} ms after the user started")
    assert 0 <= delay < 0.6

    # the pre-roll holds the user's first words, echo removed
    preroll = np.concatenate(barge.take_preroll()).astype(np.float64) / 32768
    assert len(preroll) >= 5 * B and rms(preroll) > 0.01
    assert barge.take_preroll() == []


@pytestmark_model
def test_fires_once_and_only_when_armed():
    ref = torque_voice(14)
    echo, rng = room(ref)
    mic = echo + rng.standard_normal(len(ref)) * 3e-4
    user = user_voice(12)
    mic[8 * SAMPLE_RATE:8 * SAMPLE_RATE + len(user)] += user[: len(mic) - 8 * SAMPLE_RATE]

    barge = BargeIn(load_model())
    count = []
    barge.arm(lambda: count.append(1))
    mic16 = to_int16(mic)
    for i in range(0, len(ref) - B, B):
        barge.tap(to_int16(ref[i:i + B]), SAMPLE_RATE)
        barge.feed(mic16[i:i + B])
    assert count == [1]

    idle = BargeIn(load_model())                      # never armed
    for i in range(0, len(ref) - B, B):
        assert idle.feed(mic16[i:i + B]) is False

    barge.disarm()
    assert barge.feed(mic16[:B]) is False and not barge.armed


@pytestmark_model
def test_loud_user_in_the_first_second_still_gets_through():
    ref = torque_voice(6)
    echo, rng = room(ref)
    mic = echo + rng.standard_normal(len(ref)) * 3e-4
    user = user_voice(5) * 3.0                         # clearly louder than Torque's echo
    mic[SAMPLE_RATE // 2:SAMPLE_RATE // 2 + len(user)] += user[: len(mic) - SAMPLE_RATE // 2]
    assert run(ref, mic, BargeIn(load_model())) is not None


def test_quiet_noise_alone_never_triggers():
    class AlwaysSpeech:
        def reset(self): pass
        def __call__(self, block): return 0.99          # a VAD that is fooled by everything

    barge = BargeIn(AlwaysSpeech())
    barge.arm(lambda: (_ for _ in ()).throw(AssertionError("fired")))
    rng = np.random.default_rng(0)
    for _ in range(400):
        barge.feed(to_int16(rng.standard_normal(B) * 0.002))     # -54 dBFS hiss


# ------------------------------------------------------------------ controller + stack wiring

class FakeBarge:
    def __init__(self): self.armed_with = None; self.log = []
    def tap(self, block, rate): self.log.append("tap")
    def feed(self, block): self.log.append("feed")
    def arm(self, cb): self.armed_with = cb; self.log.append("arm")
    def disarm(self): self.armed_with = None; self.log.append("disarm")
    def take_preroll(self): return ["PREROLL"]


def make_controller(script, barge=None):
    from test_controller import FakeBrain, FakeManager, FakeSpeech, FakeTTS
    from torque.core.assistant_controller import AssistantController
    from torque.core.conversation_manager import ConversationManager

    speech = FakeSpeech(script)
    tts = FakeTTS()
    mic = type("Mic", (), {})()
    speech.microphone = mic
    controller = AssistantController(FakeManager(), brain=FakeBrain(), tts=tts,
                                     conversation=ConversationManager(speech=speech), barge_in=barge)
    return controller, speech, tts, mic


def test_controller_connects_the_speaker_and_microphone_to_barge_in():
    barge = FakeBarge()
    _, _, tts, mic = make_controller([], barge)
    assert tts.tap == barge.tap and mic.on_block == barge.feed


def test_barge_in_is_off_by_default():
    controller, _, tts, mic = make_controller([])
    assert controller._barge is None and getattr(tts, "tap", None) is None and not hasattr(mic, "on_block")


def test_interrupting_stops_speech_and_keeps_what_was_heard():
    barge = FakeBarge()
    controller, speech, tts, _ = make_controller(["hello", "stop that and open chrome"], barge)

    original = tts.speak

    def speak_then_get_interrupted(text):
        assert barge.armed_with is not None            # watching while Torque talks
        barge.armed_with()                              # the user starts talking over it
        return original(text)

    tts.speak = speak_then_get_interrupted
    tts.stop = lambda: setattr(tts, "stopped", True)

    controller.activate()

    assert tts.stopped
    assert barge.log.count("arm") >= 1 and barge.armed_with is None          # disarmed afterwards
    assert speech.flushes[-1] is False and speech.prerolls[-1] == ["PREROLL"]
    assert speech.flushes[0] is True or speech.prerolls[0] is None            # normal turn flushes as before


def test_normal_turns_still_flush_and_never_pass_preroll():
    controller, speech, _, _ = make_controller(["hello"], FakeBarge())
    controller.activate()
    assert all(p is None for p in speech.prerolls)


def test_microphone_hook_and_preroll_reach_the_utterance_collector():
    from torque.audio.microphone import MicrophoneService

    seen = []

    class Vad:
        def reset(self): pass
        def process(self, block): return None

    class Stream:
        def __init__(self, callback): self.callback = callback; self.active = True
        def start(self): pass
        def stop(self): self.active = False
        def close(self): pass

    mic = MicrophoneService(vad=Vad(), stream_factory=Stream)
    mic.on_block = lambda b: seen.append(len(b))
    mic._callback(np.zeros(1024, dtype=np.int16).tobytes(), 1024, None, None)
    assert seen == [512, 512]                                   # raw blocks reach barge-in

    mic.on_block = lambda b: (_ for _ in ()).throw(RuntimeError("hook bug"))
    mic._callback(np.zeros(512, dtype=np.int16).tobytes(), 512, None, None)   # must not break capture


def test_tts_taps_every_block_it_plays():
    from torque.audio.tts_service import BLOCK_SAMPLES, TTSService

    class Engine:
        sample_rate = 22050
        def synthesize(self, text): return np.ones(BLOCK_SAMPLES * 2 + 5, dtype=np.int16)

    class Stream:
        def __init__(self, rate): self.written = []
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def write(self, block): self.written.append(len(block))

    tapped = []
    tts = TTSService(engine=Engine(), stream_factory=Stream)
    tts.tap = lambda block, rate: tapped.append((len(block), rate))
    assert tts.speak("Hello there.")
    assert [n for n, _ in tapped] == [BLOCK_SAMPLES, BLOCK_SAMPLES, 5] and {r for _, r in tapped} == {22050}

    tts.tap = lambda block, rate: (_ for _ in ()).throw(RuntimeError("tap bug"))
    assert tts.speak("Again.")                                  # a broken tap never breaks speech
