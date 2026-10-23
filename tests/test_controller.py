import threading

from torque.conversation.conversation_policy import ConversationPolicy
from torque.core.assistant_controller import AssistantController
from torque.core.conversation_manager import ConversationManager


class FakeManager:
    def get(self, _):
        return None


class FakeSpeech:
    """Scripted microphone: each item is a transcript, "" or None (silence)."""

    def __init__(self, script):
        self.script = list(script)
        self.timeouts = []
        self.stopped = False

    def listen(self, timeout=None):
        self.timeouts.append(timeout)
        return self.script.pop(0) if self.script else None

    def stop(self):
        self.stopped = True

    def reset(self):
        self.stopped = False


class FakeBrain:
    def __init__(self, replies=None):
        self.conversation_policy = ConversationPolicy()
        self.histories = []
        self.replies = replies or {}
        self.shut = False

    def process(self, history, on_status=None):
        self.histories.append(list(history))
        text = history[-1]["content"]
        if "weather" in text and on_status:
            on_status("searching", "Let me check the latest weather.")
        if text == "explode":
            raise RuntimeError("boom")
        return self.replies.get(text, f"reply to {text}")

    def shutdown(self):
        self.shut = True


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stopped = False

    def speak(self, text):
        self.spoken.append(text)

    def stop(self):
        self.stopped = True


def make(script, **kw):
    speech = FakeSpeech(script)
    tts = FakeTTS()
    brain = FakeBrain(**kw)
    controller = AssistantController(
        FakeManager(), brain=brain, tts=tts,
        conversation=ConversationManager(speech=speech),
    )
    controller.config = {**controller.config, "listen_timeout": 7.0}
    return controller, speech, brain, tts


def test_full_turn_then_goodbye():
    c, speech, brain, tts = make(["open chrome", "bye"])
    c.activate()
    assert tts.spoken == ["reply to open chrome", "Alright, see you later."]
    assert not c.conversation.active
    assert speech.timeouts[0] == 7.0


def test_silence_ends_the_conversation_quietly():
    c, _, brain, tts = make([None])
    c.activate()
    assert tts.spoken == [] and brain.histories == []
    assert not c.conversation.active


def test_noise_only_turns_are_tolerated_then_end():
    c, _, brain, _ = make(["", "", "", "should never be reached"])
    c.activate()
    assert brain.histories == []


def test_acknowledgements_are_ignored():
    c, _, brain, tts = make(["okay", "yeah", "bye"])
    c.activate()
    assert brain.histories == []
    assert tts.spoken == ["Alright, see you later."]


def test_incomplete_sentence_is_continued():
    c, speech, brain, _ = make(["open chrome and", "open discord", "bye"])
    c.activate()
    assert brain.histories[0][-1]["content"] == "open chrome and open discord"
    assert speech.timeouts[1] == c.CONTINUATION_TIMEOUT


def test_history_carries_across_turns():
    c, _, brain, _ = make(["first question", "second question", "bye"])
    c.activate()
    roles = [m["role"] for m in brain.histories[1]]
    assert roles == ["user", "assistant", "user"]


def test_search_announcement_is_spoken_before_the_answer():
    c, _, _, tts = make(["what's the weather", "bye"])
    c.activate()
    assert tts.spoken[:2] == ["Let me check the latest weather.", "reply to what's the weather"]


def test_brain_exception_does_not_kill_the_loop():
    c, _, _, tts = make(["explode", "hello", "bye"])
    c.activate()
    assert tts.spoken[0] == "Something went wrong on my side."
    assert "reply to hello" in tts.spoken


def test_cancel_interrupts_a_waiting_conversation():
    c, speech, _, tts = make([])
    started = threading.Event()

    original = speech.listen

    def blocking_listen(timeout=None):
        started.set()
        while not speech.stopped:
            threading.Event().wait(0.01)
        return None

    speech.listen = blocking_listen

    thread = threading.Thread(target=c.activate)
    thread.start()
    assert started.wait(2)

    c.toggle()   # second hotkey press

    thread.join(2)
    assert not thread.is_alive()
    assert tts.stopped
    assert not c.conversation.active


def test_second_activation_while_running_is_ignored():
    c, *_ = make([])
    assert c._lock.acquire(blocking=False)
    c.activate()          # must return immediately, not start a second loop
    c._lock.release()


def test_typed_message_gets_a_spoken_reply():
    c, _, brain, tts = make([])
    c.handle_message({"type": "text", "text": "hello there"})
    assert tts.spoken == ["reply to hello there"]


def test_cancelled_reply_is_not_spoken():
    c, _, brain, tts = make(["hello"])
    original = brain.process

    def process_and_cancel(history, on_status=None):
        c.cancel()
        return original(history, on_status)

    brain.process = process_and_cancel
    c.activate()
    assert tts.spoken == []
