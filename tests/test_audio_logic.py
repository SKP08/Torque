import numpy as np

from torque.audio.utterance import UtteranceCollector
from torque.audio.tts_service import TTSService
from torque.utils.text import split_sentences, to_speech


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def block(value=0.1):
    return np.full(512, value, dtype=np.float32)


def test_preroll_keeps_audio_before_vad_fires():
    c = UtteranceCollector(clock=Clock(), preroll_seconds=0.1)   # 3 blocks
    for i in range(10):
        c.feed(block(i), None)
    c.feed(block(99), "start")
    audio = c.audio()
    # last 3 pre-roll blocks (including the start block itself)
    assert len(audio) == 3 * 512
    assert audio[0] == 8 and audio[-1] == 99


def test_ends_after_grace_period():
    clock = Clock()
    c = UtteranceCollector(clock=clock, grace_seconds=1.0)
    c.feed(block(), "start")
    c.feed(block(), None)
    assert c.feed(block(), "end") is False
    clock.t = 0.5
    assert c.feed(block(), None) is False
    clock.t = 1.1
    assert c.feed(block(), None) is True


def test_continuation_within_grace_keeps_the_pause():
    clock = Clock()
    c = UtteranceCollector(clock=clock, grace_seconds=1.0, preroll_seconds=0.03)
    c.feed(block(1), "start")
    c.feed(block(2), "end")
    clock.t = 0.3
    c.feed(block(0), None)      # pause
    c.feed(block(3), "start")   # continues
    assert c.state == c.SPEAKING
    audio = c.audio()
    assert list(audio[::512]) == [1, 2, 0, 3]


def test_expired_works_without_new_blocks():
    clock = Clock()
    c = UtteranceCollector(clock=clock, grace_seconds=1.0)
    c.feed(block(), "start")
    c.feed(block(), "end")
    assert not c.expired()
    clock.t = 2
    assert c.expired()


def test_max_length_guard():
    c = UtteranceCollector(max_seconds=0.1)
    c.feed(block(), "start")
    done = False
    for _ in range(10):
        done = c.feed(block(), None) or done
    assert done


def test_nothing_heard_returns_none():
    c = UtteranceCollector(clock=Clock())
    c.feed(block(), None)
    assert c.audio() is None


# ---------------- TTS ----------------

class FakeChunk:
    def __init__(self, n):
        self.audio_int16_array = np.ones(n, dtype=np.int16)


class FakeVoice:
    class config:
        sample_rate = 22050

    def __init__(self):
        self.spoken = []

    def synthesize(self, text):
        self.spoken.append(text)
        yield FakeChunk(5000)


class FakeStream:
    def __init__(self, on_write=None):
        self.writes = []
        self.on_write = on_write

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def write(self, data):
        assert data.ndim == 2 and data.shape[1] == 1
        self.writes.append(len(data))
        if self.on_write:
            self.on_write()


def test_tts_streams_sentence_by_sentence():
    voice = FakeVoice()
    stream = FakeStream()
    tts = TTSService(voice=voice, stream_factory=lambda sr: stream)
    assert tts.speak("First sentence. Second one! Third?") is True
    assert voice.spoken == ["First sentence.", "Second one!", "Third?"]
    assert sum(stream.writes) == 3 * 5000


def test_tts_can_be_interrupted():
    voice = FakeVoice()
    holder = {}
    stream = FakeStream(on_write=lambda: holder["tts"].stop())
    tts = TTSService(voice=voice, stream_factory=lambda sr: stream)
    holder["tts"] = tts
    assert tts.speak("One. Two. Three. Four. Five.") is False
    assert sum(stream.writes) < 5 * 5000


def test_tts_survives_synthesis_errors():
    class Broken(FakeVoice):
        def synthesize(self, text):
            raise RuntimeError("boom")

    tts = TTSService(voice=Broken(), stream_factory=lambda sr: FakeStream())
    assert tts.speak("Hello there.") is True


# ---------------- text utils ----------------

def test_split_sentences():
    assert split_sentences("Hi there. How are you?  Fine!") == ["Hi there.", "How are you?", "Fine!"]
    assert split_sentences("") == []


def test_to_speech_cleans_markdown_and_limits_length():
    raw = "**Weather**: It is [sunny](http://x.com) today.\n- High 20\n- Low 10 http://spam.com. Extra. More. Even more."
    spoken = to_speech(raw, max_sentences=3)
    assert "*" not in spoken and "http" not in spoken and "[" not in spoken
    assert len(spoken.split(". ")) <= 4
