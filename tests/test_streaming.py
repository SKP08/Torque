import json
import threading

import numpy as np
import pytest

from torque.ai.ollama_service import OllamaService, OllamaUnavailableError
from torque.audio.chime import make_chime
from torque.system.app_registry import AppRegistry
from torque.utils.text import SentenceChunker


def chunk_all(text, size=3, **kw):
    chunker = SentenceChunker(**kw)
    out = []
    for i in range(0, len(text), size):
        out += chunker.feed(text[i:i + size])
    out += chunker.finish()
    return out


def test_chunker_splits_sentences():
    out = chunk_all("Python is a language. It is easy to learn! Try it today.")
    assert out == ["Python is a language.", "It is easy to learn!", "Try it today."]


def test_chunker_does_not_split_abbreviations_or_decimals():
    out = chunk_all("Dr. Smith paid 3.5 dollars for it. Fine.", eager_first=False)
    assert out[0] == "Dr. Smith paid 3.5 dollars for it."


def test_chunker_loses_nothing_whatever_the_piece_size():
    text = "First part, and a longer second part that keeps going on and on. Then done."
    for size in (1, 2, 5, 50):
        assert " ".join(chunk_all(text, size)).split() == text.split()


def test_chunker_eager_first_clause_comes_out_early():
    chunker = SentenceChunker(eager_first=True)
    early = chunker.feed("Sure thing, I can explain how that works in detail, ")
    assert early and early[0].startswith("Sure thing")


def test_chime_is_short_int16_audio():
    for kind in ("wake", "done"):
        audio = make_chime(kind)
        assert audio.dtype == np.int16 and 0.1 < len(audio) / 22050 < 1.0
        assert np.abs(audio).max() > 1000
        assert abs(int(audio[0])) < 50          # faded in: no click


def fake_chat(pieces, done_reason="stop"):
    def chat(**kwargs):
        assert kwargs["stream"] is True
        for p in pieces:
            yield {"message": {"content": p}, "done": False}
        yield {"message": {"content": ""}, "done": True, "done_reason": done_reason}
    return chat


def test_ollama_streams_pieces_in_order():
    llm = OllamaService(model="x", chat=fake_chat(["Hel", "lo ", "there"]))
    assert list(llm.chat_stream([])) == ["Hel", "lo ", "there"]
    assert llm.chat([]) == "Hello there"
    assert llm.truncated is False


def test_ollama_flags_truncated_replies():
    llm = OllamaService(model="x", chat=fake_chat(["cut off"], done_reason="length"))
    list(llm.chat_stream([]))
    assert llm.truncated is True


def test_ollama_down_raises_friendly_error():
    def chat(**_):
        raise ConnectionError("refused")
    llm = OllamaService(model="x", chat=chat)
    with pytest.raises(OllamaUnavailableError):
        list(llm.chat_stream([]))


class CountingScanner:
    def __init__(self, apps, gate=None):
        self.apps, self.calls, self.gate = apps, 0, gate

    def scan(self):
        self.calls += 1
        if self.gate:
            self.gate.wait(2)          # hold the background refresh
        return self.apps


def test_app_registry_writes_and_uses_cache(tmp_path):
    cache = tmp_path / "apps.json"
    apps = [{"name": "Chrome", "path": "chrome.exe"}]

    first = AppRegistry(CountingScanner(apps), cache_path=cache)
    first.load()
    assert json.loads(cache.read_text()) == apps

    gate = threading.Event()
    scanner = CountingScanner([{"name": "Edge", "path": "edge.exe"}], gate)
    second = AppRegistry(scanner, cache_path=cache)
    second.load()
    assert second.find("chrome")          # served from cache immediately
    gate.set()


def test_app_registry_ignores_corrupt_cache(tmp_path):
    cache = tmp_path / "apps.json"
    cache.write_text("{not json")
    scanner = CountingScanner([{"name": "Chrome", "path": "c.exe"}])
    registry = AppRegistry(scanner, cache_path=cache)
    registry.load()
    assert scanner.calls == 1 and registry.find("chrome")
