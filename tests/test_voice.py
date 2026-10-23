import http.server
import os
import threading
from pathlib import Path

import numpy as np
import pytest

from torque.ai.system_prompt import build_system_prompt
from torque.audio import tts_service
from torque.audio.kokoro_engine import (
    KokoroEngine, PiperEngine, load_vocab, split_phonemes, trim_silence,
)
from torque.audio.tts_service import TTSService, load_engine, measure_rtf
from torque.audio.voice_download import download


# ------------------------------------------------------------- engine unit

class Input:
    def __init__(self, name, type_): self.name, self.type = name, type_


class FakeSession:
    """Stands in for onnxruntime: records inputs, returns a tone."""

    def __init__(self, tokens_name="tokens", speed_type="tensor(float)"):
        self.calls = []
        self.inputs = [Input(tokens_name, "tensor(int64)"), Input("style", "tensor(float)"), Input("speed", speed_type)]

    def get_inputs(self): return self.inputs

    def run(self, _, feed):
        self.calls.append(feed)
        n = 24000 // 2
        tone = 0.3 * np.sin(np.linspace(0, 200, n)).astype(np.float32)
        silence = np.zeros(3000, dtype=np.float32)
        return [np.concatenate([silence, tone, silence])]


VOICES = {"bm_george": np.arange(510 * 256, dtype=np.float32).reshape(510, 1, 256) / 1e5}


def engine(session=None, **kw):
    return KokoroEngine(session or FakeSession(), VOICES, phonemize=lambda t: t.lower(), **kw)


def test_vocab_is_the_models_own():
    vocab = load_vocab()
    assert len(vocab) == 114 and vocab["a"] and vocab[" "] == 16


def test_tokens_are_wrapped_with_padding_and_style_row_matches_length():
    session = FakeSession()
    audio = engine(session).synthesize("abc")
    feed = session.calls[0]
    assert feed["tokens"][0][0] == 0 and feed["tokens"][0][-1] == 0 and feed["tokens"].shape == (1, 5)
    assert feed["tokens"].dtype == np.int64
    assert feed["style"].shape == (1, 256)
    assert np.allclose(feed["style"], VOICES["bm_george"][2])        # 3 tokens -> row 2
    assert feed["speed"].dtype == np.float32 and float(feed["speed"][0]) == 1.0
    assert audio.dtype == np.int16 and len(audio) > 0


def test_silence_is_trimmed_and_a_pause_is_added():
    audio = engine(FakeSession()).synthesize("abc")
    seconds = len(audio) / 24000
    assert 0.5 < seconds < 0.8          # 0.5 s tone + ~0.14 s pause, not +0.25 s of model silence
    assert np.all(audio[-3000:] == 0)   # the trailing pause is silent


def test_alternative_input_name_and_speed_setting():
    session = FakeSession(tokens_name="input_ids")
    engine(session, speed=1.25).synthesize("abc")
    assert "input_ids" in session.calls[0] and float(session.calls[0]["speed"][0]) == 1.25


def test_unknown_characters_are_dropped_not_fatal():
    session = FakeSession()
    assert engine(session).synthesize("a☃b") is not None
    assert session.calls[0]["tokens"].shape == (1, 4)


def test_nothing_speakable_returns_none():
    assert engine().synthesize("   ") is None
    assert engine().synthesize("☃☃") is None


def test_bad_voice_and_speed_are_rejected():
    with pytest.raises(ValueError, match="not found"):
        KokoroEngine(FakeSession(), VOICES, voice="nobody", phonemize=lambda t: t)
    with pytest.raises(ValueError, match="between 0.5 and 2.0"):
        engine(speed=3.0)


def test_long_phoneme_strings_are_split_to_fit_the_context():
    text = ("a" * 40 + ", ") * 30                  # 1260 characters
    pieces = split_phonemes(text)
    assert all(0 < len(p) <= 510 for p in pieces)
    assert "".join(pieces).replace(" ", "") == text.replace(" ", "")
    session = FakeSession()
    engine(session).synthesize(text)
    assert len(session.calls) == len(pieces) and all(c["tokens"].shape[1] <= 512 for c in session.calls)


def test_trim_silence():
    audio = np.concatenate([np.zeros(5000), np.ones(100) * 0.5, np.zeros(5000)]).astype(np.float32)
    assert 100 <= len(trim_silence(audio)) <= 100 + 2 * 600
    assert len(trim_silence(np.zeros(100, dtype=np.float32))) == 0


# ----------------------------------------------------- engine selection

BASE = {"tts_engine": "auto", "kokoro_model": "model.onnx", "kokoro_voice": "bm_george",
        "kokoro_language": "en-gb", "tts_speed": 1.0, "piper_voice": "x"}


class Marker:
    sample_rate = 24000
    def __init__(self, name): self.name = name
    def synthesize(self, text): return np.ones(24000, dtype=np.int16)


@pytest.fixture
def kokoro_files(tmp_path, monkeypatch):
    folder = tmp_path / "kokoro"
    folder.mkdir()
    (folder / "model.onnx").write_text("x")
    (folder / "voices-v1.0.bin").write_text("x")
    monkeypatch.setattr(tts_service, "MODELS_DIR", tmp_path)
    return folder


def pick(config, **kw):
    return load_engine(config, kokoro_factory=lambda *a: Marker("kokoro"),
                       piper_factory=lambda: type("V", (), {"config": type("C", (), {"sample_rate": 22050})(), "synthesize": lambda s, t: []})(), **kw)


def test_auto_uses_kokoro_when_installed_and_fast(kokoro_files):
    assert pick(BASE, rtf_probe=lambda e: 0.3).name == "kokoro"


def test_auto_falls_back_to_piper_when_kokoro_is_too_slow(kokoro_files):
    assert isinstance(pick(BASE, rtf_probe=lambda e: 1.6), PiperEngine)


def test_forcing_kokoro_ignores_the_speed_check(kokoro_files):
    assert pick({**BASE, "tts_engine": "kokoro"}, rtf_probe=lambda e: 9.9).name == "kokoro"


def test_auto_without_files_uses_piper(tmp_path, monkeypatch):
    monkeypatch.setattr(tts_service, "MODELS_DIR", tmp_path)
    assert isinstance(pick(BASE), PiperEngine)


def test_forcing_kokoro_without_files_explains_how_to_get_them(tmp_path, monkeypatch):
    monkeypatch.setattr(tts_service, "MODELS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError, match="voice_download"):
        pick({**BASE, "tts_engine": "kokoro"})


def test_a_crashing_kokoro_does_not_stop_torque(kokoro_files):
    def boom(*a): raise RuntimeError("bad onnx")
    engine = load_engine(BASE, kokoro_factory=boom,
                         piper_factory=lambda: type("V", (), {"config": type("C", (), {"sample_rate": 22050})()})())
    assert isinstance(engine, PiperEngine)


def test_piper_only_setting_never_touches_kokoro(kokoro_files):
    called = []
    load_engine({**BASE, "tts_engine": "piper"}, kokoro_factory=lambda *a: called.append(1),
                piper_factory=lambda: type("V", (), {"config": type("C", (), {"sample_rate": 22050})()})())
    assert called == []


def test_measure_rtf_math():
    class Timed:
        sample_rate = 24000
        def synthesize(self, t): return np.zeros(48000, dtype=np.int16)      # 2 s of audio
    assert measure_rtf(Timed()) < 0.5


def test_tts_service_speaks_through_any_engine():
    written = []

    class Stream:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def write(self, block): written.append(len(block))

    service = TTSService(engine=Marker("k"), stream_factory=lambda rate: Stream())
    assert service.sample_rate == 24000
    assert service.speak("Hello there. How are you?") is True
    assert sum(written) == 2 * 24000


# --------------------------------------------------------------- download

def test_download_is_atomic_and_checks_size(tmp_path):
    served = tmp_path / "srv"; served.mkdir()
    (served / "good.bin").write_bytes(b"x" * 2000)
    (served / "short.bin").write_bytes(b"x" * 10)

    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(served), **k)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    out = tmp_path / "out"

    try:
        path = download("good.bin", 1000, out, base=base, progress=False)
        assert path.read_bytes() == b"x" * 2000 and not list(out.glob("*.part"))

        with pytest.raises(RuntimeError, match="incompletely"):
            download("short.bin", 1000, out, base=base, progress=False)
        assert not (out / "short.bin").exists() and not list(out.glob("*.part"))     # nothing half-written

        assert download("good.bin", 1000, out, base="http://127.0.0.1:1", progress=False) == path   # cached: no network
    finally:
        server.shutdown()


# ---------------------------------------------------------------- persona

def test_butler_prompt_and_title():
    text = build_system_prompt("butler", "sir")
    assert "butler" in text and 'Address the user as "sir"' in text
    assert "butler" not in build_system_prompt("plain", "sir")
    assert "Address the user" not in build_system_prompt("butler", "")


def test_prompt_lists_current_abilities_so_the_model_does_not_deny_them():
    text = build_system_prompt()
    for ability in ("screenshots", "Read the screen", "unzip", "timers"):
        assert ability in text


# ------------------------------------------------- the real model, if present

REAL = Path(os.environ.get("TORQUE_KOKORO_DIR", "/tmp/kokoro"))


@pytest.mark.skipif(not (REAL / "kokoro-v1.0.int8.onnx").exists(), reason="Kokoro files not downloaded")
def test_real_model_produces_speech_shaped_audio():
    pytest.importorskip("phonemizer"); pytest.importorskip("espeakng_loader")
    e = KokoroEngine.load(REAL / "kokoro-v1.0.int8.onnx", REAL / "voices-v1.0.bin")
    audio = e.synthesize("The capital of India is New Delhi.")
    seconds = len(audio) / 24000
    assert 1.5 < seconds < 4.5                       # about two and a half seconds of speech
    assert np.abs(audio).max() > 3000                # audible
    assert np.abs(audio).max() <= 32767
    # speech has energy modulation (syllables); a constant buzz would not
    frames = np.abs(audio[: len(audio) // 480 * 480].astype(float)).reshape(-1, 480).mean(axis=1)
    assert frames.std() / frames.mean() > 0.4
    # a longer text is longer audio, and a different sentence differs
    longer = e.synthesize("The capital of India is New Delhi, and it sits on the banks of the Yamuna river.")
    assert len(longer) > len(audio) * 1.5


@pytest.mark.skipif(not (REAL / "kokoro-v1.0.int8.onnx").exists(), reason="Kokoro files not downloaded")
def test_real_model_speech_is_intelligible_round_trip():
    """Synthesise, then recognise with an independent offline recogniser."""
    pocketsphinx = pytest.importorskip("pocketsphinx")
    signal = pytest.importorskip("scipy.signal")
    pytest.importorskip("phonemizer")
    e = KokoroEngine.load(REAL / "kokoro-v1.0.int8.onnx", REAL / "voices-v1.0.bin")
    audio = e.synthesize("Opening Chrome and setting the volume to thirty percent.").astype(np.float32) / 32768
    pcm = (signal.resample_poly(audio, 2, 3) * 32767).astype(np.int16)         # 24 kHz -> 16 kHz
    decoder = pocketsphinx.Decoder(samprate=16000)
    decoder.start_utt(); decoder.process_raw(pcm.tobytes(), False, True); decoder.end_utt()
    heard = decoder.hyp().hypstr.split()
    expected = "opening chrome and setting the volume to thirty percent".split()
    assert sum(w in heard for w in expected) >= len(expected) - 1
