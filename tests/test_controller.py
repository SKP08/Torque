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
        self.flushes = []
        self.stopped = False
        self.interrupted = False
        self.level_callback = None

    def listen(self, timeout=None, flush=False, max_seconds=None):
        self.timeouts.append(timeout)
        self.flushes.append(flush)
        return self.script.pop(0) if self.script else None

    def set_level_callback(self, callback):
        self.level_callback = callback

    def interrupt(self):
        self.interrupted = True

    def close(self):
        pass

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

    def process_stream(self, history, on_status=None, **_):
        text = history[-1]["content"]
        if "weather" in text:
            # The real brain yields its search announcement as a sentence.
            yield "Let me check the latest weather."
            if on_status:
                on_status("searching", "Searching the web...")
        reply = self.process(history, None)
        if reply:
            yield reply

    def process(self, history, on_status=None):
        self.histories.append(list(history))
        text = history[-1]["content"]
        if text == "explode":
            raise RuntimeError("boom")
        return self.replies.get(text, f"reply to {text}")

    def shutdown(self):
        self.shut = True


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stopped = False

    def speak(self, speech):
        # Accepts a string or a generator of sentences, like TTSService.
        if not isinstance(speech, str):
            speech = " ".join(speech)
        if speech:
            self.spoken.append(speech)
        return True

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
    assert tts.spoken[0] == "Let me check the latest weather. reply to what's the weather"


def test_brain_exception_does_not_kill_the_loop():
    c, _, _, tts = make(["explode", "hello", "bye"])
    c.activate()
    assert tts.spoken[0] == "Something went wrong on my side."
    assert "reply to hello" in tts.spoken


def test_cancel_interrupts_a_waiting_conversation():
    c, speech, _, tts = make([])
    started = threading.Event()

    original = speech.listen

    def blocking_listen(timeout=None, **_):
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


# ---------------------------------------------------------------- wake word

class WakeSpeech(FakeSpeech):
    """Ambient audio first (for the wake loop), then the conversation script."""

    def __init__(self, ambient, script):
        super().__init__(script)
        self.ambient = list(ambient)
        self.resets = 0

    def listen(self, timeout=None, flush=False, max_seconds=None):
        if max_seconds is not None:               # the idle wake listener
            return self.ambient.pop(0) if self.ambient else None
        return super().listen(timeout, flush)

    def reset(self):
        self.resets += 1


def make_wake(ambient, script):
    speech = WakeSpeech(ambient, script)
    chimes = []
    controller = AssistantController(
        FakeManager(), brain=FakeBrain(), tts=FakeTTS(),
        conversation=ConversationManager(speech=speech),
        chime=chimes.append,
    )
    controller.wake_enabled = True
    return controller, speech, chimes


def test_wake_word_alone_starts_a_listening_conversation():
    c, _, _ = make_wake(["hey torque"], [])
    trigger = c._wait_for_trigger()
    assert trigger.source == "wake" and trigger.text == ""


def test_one_breath_command_is_carried_in_the_trigger():
    c, _, _ = make_wake(["Hey Torque, open Chrome"], [])
    trigger = c._wait_for_trigger()
    assert trigger.text == "open Chrome"


def test_speech_not_for_torque_is_ignored():
    c, _, _ = make_wake(["I think the torque wrench is in the garage"], [])
    assert c._wait_for_trigger() is None


def test_hotkey_activation_wins_over_listening():
    c, _, _ = make_wake([], [])
    c._activation.set()
    assert c._wait_for_trigger().source == "hotkey"


def test_chime_plays_only_when_no_command_was_given():
    c, _, chimes = make_wake([], ["bye"])
    c.activate()
    assert chimes == ["wake"]

    c2, _, chimes2 = make_wake([], ["bye"])
    c2.activate(first_text="open chrome")
    assert chimes2 == []
    assert c2.tts.spoken[0] == "reply to open chrome"


def test_main_loop_runs_a_full_wake_conversation():
    c, speech, _ = make_wake(["hey torque what time is it"], ["bye"])
    c.start()
    for _ in range(200):
        if c.tts.spoken and not c.conversation.active and c._lock.acquire(False):
            c._lock.release()
            break
        threading.Event().wait(0.02)
    c.shutdown()
    assert c.tts.spoken[0] == "reply to what time is it"
    assert speech.resets >= 1                  # buffer cleared after the reply


def test_ui_activate_message_starts_a_conversation():
    c, _, chimes = make_wake([], [])          # no main thread: runs directly
    c.handle_message({"type": "activate"})
    assert chimes == ["wake"]
    assert not c.conversation.active
