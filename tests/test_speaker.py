import os
from pathlib import Path

import numpy as np
import pytest

from torque.audio import speaker
from torque.audio.speaker import SpeakerEncoder, VoiceGate, cosine, enrol, fbank, load_gate, mel_banks

MODEL = Path(os.environ.get("TORQUE_SPEAKER_MODEL", "/tmp/claude-0/spk/wespeaker_en_voxceleb_resnet34.onnx"))
KOKORO = Path(os.environ.get("TORQUE_KOKORO_DIR", "/tmp/kokoro"))
SAMPLE = Path(__file__).parent / "data" / "speech_sample.wav"


def speech_sample():
    import wave
    with wave.open(str(SAMPLE)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768


class FakeEncoder:
    """Embeds a clip as its [mean, std] pair: deterministic and distinguishable."""
    def embed(self, audio):
        if audio is None or len(audio) < 0.8 * 16000:
            return None
        v = np.array([float(np.mean(audio)) + 1.0, float(np.std(audio)) * 10, 0.5])
        return v / np.linalg.norm(v)


def test_fbank_shape_and_normalisation():
    f = fbank(speech_sample())
    assert f.shape == (1 + (len(speech_sample()) - 400) // 160, 80)
    assert np.abs(f.mean(axis=0)).max() < 1e-4 and np.isfinite(f).all()
    assert fbank(np.zeros(100)).shape == (0, 80)
    assert np.isfinite(fbank(np.zeros(16000))).all()                      # digital silence doesn't produce NaN/-inf


def test_mel_banks_cover_the_spectrum():
    banks = mel_banks()
    assert banks.shape == (80, 257) and (banks >= 0).all()
    assert (banks.sum(axis=1) > 0).all() and banks[0].argmax() < banks[-1].argmax()


def test_enrol_needs_usable_clips_and_returns_a_unit_profile():
    clips = [np.random.default_rng(i).standard_normal(16000 * 2).astype(np.float32) * 0.1 for i in range(3)]
    profile = enrol(FakeEncoder(), clips)
    assert abs(np.linalg.norm(profile) - 1) < 1e-6
    with pytest.raises(ValueError):
        enrol(FakeEncoder(), [clips[0], np.zeros(100, dtype=np.float32)])


def test_gate_accepts_match_rejects_other_and_never_locks_you_out_when_unsure():
    owner = np.random.default_rng(1).standard_normal(32000).astype(np.float32) * 0.1
    stranger = np.random.default_rng(2).standard_normal(32000).astype(np.float32) * 0.5 + 0.3
    gate = VoiceGate(FakeEncoder(), FakeEncoder().embed(owner), threshold=0.9)
    assert gate.accepts(owner) and gate.last_score > 0.9
    assert not gate.accepts(stranger)
    assert gate.accepts(None) and gate.accepts(np.zeros(100, dtype=np.float32))   # too short: can't tell -> allow


def test_load_gate_is_off_or_safe(tmp_path):
    assert load_gate({}, tmp_path / "m", tmp_path / "p") is None
    assert load_gate({"voice_lock_enabled": True}, tmp_path / "missing.onnx", tmp_path / "p.npy") is None


@pytest.mark.skipif(not MODEL.exists(), reason="speaker model not downloaded")
def test_real_model_embeds_and_rejects_short_clips():
    encoder = SpeakerEncoder(MODEL)
    vector = encoder.embed(speech_sample())
    assert vector.shape == (256,) and abs(np.linalg.norm(vector) - 1) < 1e-6
    assert encoder.embed(speech_sample()[:8000]) is None
    # same audio twice -> identical print
    assert cosine(vector, encoder.embed(speech_sample())) > 0.999


@pytest.mark.skipif(not MODEL.exists() or not (KOKORO / "kokoro-v1.0.int8.onnx").exists(),
                    reason="speaker or kokoro model not available")
def test_real_model_tells_different_voices_apart():
    from torque.audio.kokoro_engine import KokoroEngine

    encoder = SpeakerEncoder(MODEL)
    texts = ["Hey Torque, what time is it?", "Open Chrome and play some music for me please.",
             "The quick brown fox jumps over the lazy dog.", "Remind me in ten minutes to stretch my legs."]

    def prints(voice, language):
        engine = KokoroEngine.load(KOKORO / "kokoro-v1.0.int8.onnx", KOKORO / "voices-v1.0.bin",
                                   voice=voice, language=language)
        out = []
        for text in texts:
            audio = engine.synthesize(text).astype(np.float32) / 32768
            n = int(len(audio) * 16000 / engine.sample_rate)
            out.append(encoder.embed(np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio)))
        return out

    owner = prints("bm_george", "en-gb")
    other = prints("am_michael", "en-us")
    third = prints("af_heart", "en-us")

    profile = enrol_from_prints(owner[:2])
    same = [cosine(p, profile) for p in owner[2:]]
    different = [cosine(p, profile) for p in other + third]
    print(f"\nsame voice: {min(same):.2f}..{max(same):.2f}   other voices: {min(different):.2f}..{max(different):.2f}")
    assert min(same) > 0.55 > max(different) + 0.1                 # a threshold of 0.5 separates them with margin


def enrol_from_prints(prints):
    centre = np.mean(prints, axis=0)
    return centre / np.linalg.norm(centre)


# ----------------------------------------------------------------- controller gating

def make_controller(gate):
    from test_controller import FakeBrain, FakeManager, FakeSpeech, FakeTTS
    from torque.core.assistant_controller import AssistantController
    from torque.core.conversation_manager import ConversationManager

    speech = FakeSpeech(["hey torque open chrome"])
    speech.microphone = type("Mic", (), {"last_audio": np.zeros(32000, dtype=np.float32)})()
    controller = AssistantController(FakeManager(), brain=FakeBrain(), tts=FakeTTS(),
                                     conversation=ConversationManager(speech=speech), voice_gate=gate)
    controller.wake_enabled = True
    controller._needs_reset = False
    return controller


class Gate:
    def __init__(self, ok): self.ok = ok; self.seen = []
    def accepts(self, audio): self.seen.append(audio); return self.ok


def test_wake_word_from_the_wrong_voice_is_ignored():
    gate = Gate(False)
    controller = make_controller(gate)
    controller.conversation.speech.reset = lambda: None
    assert controller._wait_for_trigger() is None and len(gate.seen) == 1


def test_wake_word_from_the_owner_starts_a_conversation():
    controller = make_controller(Gate(True))
    controller.conversation.speech.reset = lambda: None
    trigger = controller._wait_for_trigger()
    assert trigger is not None and trigger.source == "wake"


def test_no_gate_means_no_change():
    controller = make_controller(None)
    controller.conversation.speech.reset = lambda: None
    assert controller._wait_for_trigger().source == "wake"
