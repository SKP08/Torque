import pytest

from torque.web.search_router import SearchRouter

router = SearchRouter()


@pytest.mark.parametrize("text", [
    "what's the weather like",
    "will it rain tomorrow",
    "latest news",
    "what's the score of the match",
    "who is the prime minister of canada",
    "who won the world cup",
    "bitcoin price",
    "how is the market doing today",
    "what's going on in the world",
    "best laptop under 1000 dollars",
    "iphone vs pixel",
    "what's the latest python version",
    "latest nvidia driver",
    "tell me about CVE-2024-3094",
    "what is the latest on the spacex launch",
    "what's tesla stock price",
])
def test_needs_web(text):
    assert router.needs_web(text), text


@pytest.mark.parametrize("text", [
    "do you understand me",            # "under"
    "I took the train",                # "rain"
    "what's your brain like",          # "rain"
    "can you deliver a speech",        # "live"
    "how do I share a file in python", # "share"
    "explain how a stock exchange works",
    "what is a renewable resource",
    "tell me a joke",
    "open chrome",
    "how do I update my resume",
    "who is Ada Lovelace",
    "what is the current directory in linux",
])
def test_does_not_need_web(text):
    assert not router.needs_web(text), text


def test_announcements():
    assert "weather" in router.announcement("will it rain")
    assert "news" in router.announcement("latest news")
    assert "sports" in router.announcement("who won the match")
    assert router.announcement("something else") == "I'll search the web for that."
