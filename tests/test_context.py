import pytest

from torque.desktop.context import active_window, classify
from torque.screen.screen_assistant import ScreenAssistant, is_screen_request
from torque.skills.context_skills import build_context_skills
from torque.skills.registry import SkillRegistry


def ctx(process, title):
    return active_window(lambda: (process, title))


def test_friendly_names_and_description():
    c = ctx("chrome.exe", "Kerberos - Wikipedia - Google Chrome")
    assert c.app == "Chrome" and c.describe() == "Chrome - Kerberos - Wikipedia - Google Chrome"
    assert ctx("somethingnew.exe", "x").app == "Somethingnew"
    assert ctx("Code.exe", "main.py").app == "VS Code"


def test_private_windows_never_leak_their_titles():
    for proc, title in (("KeePassXC.exe", "Vault"), ("chrome.exe", "Bank - Incognito"),
                        ("msedge.exe", "InPrivate Browsing"), ("firefox.exe", "Private Browsing"),
                        ("x.exe", "Enter your password")):
        c = ctx(proc, title)
        assert c.private and c.title == ""
        assert title.split()[0] not in c.describe() or c.app in c.describe()
        assert "private window" in c.describe() and "private window" in c.spoken()


def test_unreadable_or_failing_provider_gives_none():
    assert active_window(lambda: ("", "")) is None

    def boom():
        raise OSError("no desktop")

    assert active_window(boom) is None


def test_active_window_skill_by_voice():
    reg = SkillRegistry(build_context_skills(lambda: ctx("code.exe", "brain.py - torque")))
    for phrase in ("what app am I in", "which window is active", "what am I working on",
                   "what's the active window", "what window am I on right now"):
        said = reg.handle(phrase)
        assert said and "VS Code" in said and "brain.py" in said, phrase
    assert SkillRegistry(build_context_skills(lambda: None)).handle("what app am i in") == \
        "I can't tell which window is active."


def test_context_phrases_do_not_catch_other_things():
    reg = SkillRegistry(build_context_skills(lambda: ctx("code.exe", "x")))
    for phrase in ("what is the capital of india", "what am I allergic to", "where am i going to eat", "open code"):
        assert reg.handle(phrase) is None, phrase


@pytest.mark.parametrize("phrase", ["summarize this", "explain this page", "draft a reply to this",
                                    "write a response to that", "what does this page say", "tldr this",
                                    "what's this article about"])
def test_more_screen_requests(phrase):
    assert is_screen_request(phrase)


def test_screen_assistant_gives_the_model_the_active_window():
    seen = []

    class LLM:
        truncated = False
        def chat_stream(self, messages):
            seen.append(messages)
            yield "It is a login error."

    class Reader:
        def read(self): return "Error 401 unauthorized. Please sign in again to continue."

    assistant = ScreenAssistant(LLM(), Reader(), context_fn=lambda: ctx("chrome.exe", "Sign in - Chrome"))
    list(assistant.answer("explain this error"))
    assert "Active window: Chrome - Sign in - Chrome" in seen[0][1]["content"]

    seen.clear()
    list(ScreenAssistant(LLM(), Reader(), context_fn=lambda: ctx("keepass.exe", "Secret vault")).answer("explain this"))
    assert "Secret vault" not in seen[0][1]["content"] and "private window" in seen[0][1]["content"]

    seen.clear()
    list(ScreenAssistant(LLM(), Reader(), context_fn=lambda: (_ for _ in ()).throw(RuntimeError())).answer("explain this"))
    assert seen and "Active window" not in seen[0][1]["content"]
