from pathlib import Path

import pytest

from torque.ai.brain import TorqueBrain
from torque.skills.backend import UnsupportedBackend
from torque.skills.pc_control import build_pc_skills
from torque.skills.registry import SkillRegistry, normalise

from test_brain import FakeContext, FakeLauncher, FakeLLM, FakeMemory, FakeWeb, InlineWorker


class FakeBackend:
    def __init__(self):
        self.calls = []
        self.brightness = 50

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, *args))
        return record

    def screenshot(self):
        self.calls.append(("screenshot",))
        return Path("/pics/Torque/shot.png")

    def get_brightness(self):
        return self.brightness

    def set_brightness(self, level):
        self.calls.append(("set_brightness", level))


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


@pytest.fixture
def setup():
    backend, clock = FakeBackend(), Clock()
    return SkillRegistry(build_pc_skills(backend), clock=clock), backend, clock


@pytest.mark.parametrize("text, call", [
    ("volume up", ("volume_step", "up", 5)),
    ("Turn the volume down.", ("volume_step", "down", 5)),
    ("louder", ("volume_step", "up", 5)),
    ("Hey Torque, make it quieter", ("volume_step", "down", 5)),
    ("set the volume to 30", ("set_volume", 30)),
    ("volume 80 percent", ("set_volume", 80)),
    ("mute", ("media", "mute")),
    ("unmute the sound", ("media", "mute")),
    ("pause the music", ("media", "play_pause")),
    ("pause", ("media", "play_pause")),
    ("resume", ("media", "play_pause")),
    ("next song", ("media", "next")),
    ("skip this track", ("media", "next")),
    ("previous song", ("media", "previous")),
    ("lock my computer", ("lock",)),
    ("lock the screen", ("lock",)),
    ("show desktop", ("show_desktop",)),
    ("minimize everything", ("show_desktop",)),
    ("switch window", ("switch_window",)),
    ("take a screenshot", ("screenshot",)),
    ("set brightness to 40", ("set_brightness", 40)),
    ("brighter", ("set_brightness", 70)),
    ("dim the screen", ("set_brightness", 30)),
])
def test_safe_skills_run_immediately(setup, text, call):
    registry, backend, _ = setup
    assert registry.handle(text)
    assert call in backend.calls


@pytest.mark.parametrize("text", [
    "tell me a joke", "how do I mute a discord user", "play despacito",
    "what is the volume of a sphere", "open chrome", "i need to take a break",
    "the next song on the album is great", "pause for a second and think",
    "lock down the argument", "stop talking", "shut the door",
])
def test_ordinary_sentences_are_not_commands(setup, text):
    registry, backend, _ = setup
    assert registry.handle(text) is None
    assert backend.calls == []


def test_volume_is_clamped(setup):
    registry, backend, _ = setup
    registry.handle("set the volume to 250")
    assert ("set_volume", 100) in backend.calls


def test_power_actions_need_confirmation(setup):
    registry, backend, _ = setup
    reply = registry.handle("shut down the computer")
    assert "Say yes" in reply and backend.calls == []
    assert registry.awaiting_confirmation

    assert registry.handle("yes") == "Shutting down."
    assert backend.calls == [("shutdown",)]
    assert not registry.awaiting_confirmation


@pytest.mark.parametrize("answer", ["no", "cancel", "never mind"])
def test_refusing_cancels(setup, answer):
    registry, backend, _ = setup
    registry.handle("restart my pc")
    assert registry.handle(answer) == "Okay, cancelled."
    assert backend.calls == []


def test_unrelated_sentence_drops_the_pending_action(setup):
    registry, backend, _ = setup
    registry.handle("put the computer to sleep")
    assert registry.handle("what's the weather") is None
    assert registry.handle("yes") is None            # nothing pending any more
    assert backend.calls == []


def test_confirmation_expires(setup):
    registry, backend, clock = setup
    registry.handle("shutdown")
    clock.t = 31
    assert not registry.awaiting_confirmation
    assert registry.handle("yes") is None
    assert backend.calls == []


def test_failures_are_spoken_not_raised():
    class Broken(FakeBackend):
        def media(self, key):
            raise OSError("no")

    registry = SkillRegistry(build_pc_skills(Broken()))
    assert registry.handle("mute") == "I couldn't do that."


def test_unsupported_platform_says_so():
    registry = SkillRegistry(build_pc_skills(UnsupportedBackend()))
    assert registry.handle("mute") == "That only works on Windows."


def test_normalise_strips_polite_filler():
    assert normalise("Hey, could you please mute!") == "mute"


# --------------------------------------------------------------- in the brain

def make_brain(registry):
    return TorqueBrain(
        llm=FakeLLM(), web=FakeWeb(), launcher=FakeLauncher(), memory=FakeMemory(),
        context=FakeContext(), worker=InlineWorker(), skills=registry, screen=False, agent=False, info=False,
    )


def say(brain, text):
    return " ".join(brain.process_stream([{"role": "user", "content": text}]))


def test_brain_runs_skill_before_chat_and_llm_is_untouched(setup):
    registry, backend, _ = setup
    brain = make_brain(registry)
    assert say(brain, "set the volume to 20") == "Volume 20 percent."
    assert brain.llm.calls == []


def test_bare_yes_reaches_the_pending_skill_in_the_brain(setup):
    registry, backend, _ = setup
    brain = make_brain(registry)
    assert "Say yes" in say(brain, "restart the computer")
    assert brain.awaiting_confirmation
    assert say(brain, "yeah") == "Restarting."
    assert ("restart",) in backend.calls


def test_yes_is_ignored_when_nothing_is_pending(setup):
    registry, _, _ = setup
    assert say(make_brain(registry), "yes") == ""
