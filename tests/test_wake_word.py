import pytest

from torque.conversation.wake_word import match_wake_word


@pytest.mark.parametrize("text,remainder", [
    ("Hey Torque", ""),
    ("Hey, Torque.", ""),
    ("hey torque open chrome", "open chrome"),
    ("Hey Torque, what's the weather in Toronto?", "what's the weather in Toronto?"),
    ("OK Torque. Open Spotify and then open Discord", "Open Spotify and then open Discord"),
    ("okay torque", ""),
    ("Hi Torque!", ""),
    ("Torque, what time is it", "what time is it"),
    ("torque", ""),
    ("Torque's listening", "listening"),         # possessive form Whisper sometimes writes
    ("um hey torque close discord", "close discord"),
    # Whisper mishearings
    ("Hey Tork, open chrome", "open chrome"),
    ("hey torch what's the time", "what's the time"),
    ("Hey Torques open chrome", "open chrome"),
    ("hey torgue", ""),
    ("Hey Tor, are you there", "are you there"),
])
def test_wakes(text, remainder):
    match = match_wake_word(text)
    assert match.matched, text
    assert match.remainder == remainder


@pytest.mark.parametrize("text", [
    "",
    "open chrome",
    "what time is it",
    "hey there how are you",
    "hey siri what's the weather",
    "tork",                                   # weak alias needs a greeting
    "torch the thing",                        # weak alias needs a greeting
    "talk to me",
    "hey talk to me",
    "the torque on this bolt is too low",     # not at the start
    "i think torque is important",
    "turkey sandwich",
    "tourist information",
    "store",
])
def test_does_not_wake(text):
    assert not match_wake_word(text).matched, text


def test_greeted_flag():
    assert match_wake_word("hey torque").greeted
    assert not match_wake_word("torque open chrome").greeted


def test_remainder_keeps_original_casing():
    assert match_wake_word("Hey Torque, explain TCP vs UDP").remainder == "explain TCP vs UDP"
