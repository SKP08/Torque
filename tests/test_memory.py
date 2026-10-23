import json

import pytest

from torque.memory.memory_retriever import MemoryRetriever
from torque.memory.memory_service import MemoryService, normalize_key
from torque.memory.memory_store import MemoryStore


@pytest.fixture
def store(tmp_path):
    s = MemoryStore(tmp_path / "memory.db")
    yield s
    s.close()


def make_service(store, reply):
    return MemoryService(
        store=store,
        model="test",
        chat=lambda **kwargs: {"message": {"content": reply}},
    )


def test_save_updates_and_keeps_created_at(store):
    service = make_service(store, "{}")
    service.remember("laptop", "ASUS", "device")
    first = store.conn.execute("SELECT created_at FROM memories").fetchone()[0]

    service.remember("laptop", "Lenovo", "device")

    rows = store.conn.execute("SELECT value, created_at FROM memories").fetchall()
    assert rows == [("Lenovo", first)]


def test_extract_saves_valid_fact(store):
    reply = json.dumps({"save": True, "key": "Laptop RAM", "value": "32 GB", "category": "Device"})
    make_service(store, reply).extract("my laptop has 32 GB of RAM")
    assert store.get("laptop_ram") == "32 GB"


@pytest.mark.parametrize("reply", [
    "not json",
    '{"save": true}',                                  # missing key/value
    '{"save": true, "key": "x"}',
    '["list"]',
    '{"save": false}',
])
def test_extract_survives_bad_model_output(store, reply):
    make_service(store, reply).extract("my laptop has 32 GB of RAM")
    assert store.get_all() == []


def test_extract_survives_llm_errors(store):
    def boom(**kwargs):
        raise ConnectionError("ollama down")

    MemoryService(store=store, model="t", chat=boom).extract("my name is Shubh Patel")
    assert store.get_all() == []


@pytest.mark.parametrize("text,expected", [
    ("my laptop has 32 GB of RAM", True),
    ("I live in Canada", True),
    ("call me Shubh", True),
    ("what is my laptop's RAM", False),
    ("open chrome", False),
    ("my name", False),
])
def test_should_extract_gate(store, text, expected):
    assert make_service(store, "{}").should_extract(text) is expected


def test_retrieval_is_word_based_not_substring(store):
    service = make_service(store, "{}")
    service.remember("laptop_ram", "32 GB", "device")
    service.remember("favorite_language", "Python", "preference")
    retriever = MemoryRetriever(store)

    def keys(text):
        return [m["key"] for m in retriever.retrieve([{"role": "user", "content": text}])]

    assert keys("how much ram does my laptop have") == ["laptop_ram"]
    assert keys("what language do i like") == ["favorite_language"]
    assert keys("write a program for me") == []      # "ram" inside "program"
    assert keys("what do you know about me") != []   # recall-all


def test_forget(store):
    service = make_service(store, "{}")
    service.remember("country", "Canada", "personal")
    service.forget("Country")
    assert store.get("country") is None


def test_normalize_key():
    assert normalize_key(" Favorite Language! ") == "favorite_language"
