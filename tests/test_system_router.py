import pytest

from torque.system.system_router import SystemRouter

router = SystemRouter()


def cmd(action, target, explicit=True):
    return {"action": action, "target": target, "explicit": explicit}


def test_simple_open_and_close():
    assert router.route("open chrome") == cmd("open", "chrome")
    assert router.route("Launch Spotify.") == cmd("open", "spotify")
    assert router.route("close discord") == cmd("close", "discord")


def test_polite_and_filler_words_are_removed():
    assert router.route("can you please open up the chrome app") == cmd("open", "chrome")
    assert router.route("open chrome please") == cmd("open", "chrome")


def test_sequences():
    expected = {
        "action": "sequence",
        "commands": [cmd("open", "chrome"), cmd("open", "discord")],
    }
    assert router.route("open chrome, open discord") == expected
    assert router.route("open chrome and then open discord") == expected
    assert router.route("open chrome and open discord") == expected
    # Whisper without punctuation:
    assert router.route("open edge open file explorer")["commands"] == [
        cmd("open", "edge"), cmd("open", "file explorer")
    ]


def test_weak_verbs_are_marked_not_explicit():
    assert router.route("start the timer") == cmd("open", "timer", explicit=False)
    assert router.route("quit smoking tips") == cmd("close", "smoking tips", explicit=False)


def test_phrases_stay_together():
    # "open" after "the" is part of the target, not a second command.
    assert router.route("close the open window") == cmd("close", "open window")


@pytest.mark.parametrize("text", ["", "hello there", "what time is it", "open", "run", "exit"])
def test_not_commands(text):
    assert router.route(text) is None
