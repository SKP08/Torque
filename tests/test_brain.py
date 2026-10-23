import pytest

from torque.ai.ollama_service import OllamaUnavailableError
from torque.ai.brain import TorqueBrain
from torque.system.system_commands import ActionResult
from torque.web.search_result import SearchResult


class FakeLLM:
    def __init__(self, reply="LLM reply"):
        self.reply = reply
        self.calls = []

    truncated = False

    def chat_stream(self, messages):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        # Deliver in small pieces, like a real token stream.
        words = self.reply.split(" ")
        for i, word in enumerate(words):
            yield word if i == 0 else " " + word

    def chat(self, messages):
        return "".join(self.chat_stream(messages))

    def warm_up(self):
        pass


class FakeWeb:
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return SearchResult(answer="It is **sunny**. See http://x.com for more.", sources=[])


class FakeLauncher:
    def __init__(self, known=("chrome", "discord")):
        self.known = known
        self.opened, self.closed = [], []

    def launch(self, query):
        if query in self.known:
            self.opened.append(query)
            return ActionResult(True, f"Opening {query.title()}.")
        return ActionResult(False, f"I couldn't find {query} on your computer.")

    def close(self, query):
        if query in self.known:
            self.closed.append(query)
            return ActionResult(True, f"Closing {query.title()}.")
        return ActionResult(False, f"I couldn't find {query} on your computer.")


class FakeMemory:
    def __init__(self):
        self.extracted = []

    def should_extract(self, text):
        return "my " in text

    def extract(self, text):
        self.extracted.append(text)


class FakeContext:
    def build(self, history):
        return list(history)


class InlineWorker:
    def submit(self, name, func, *args):
        func(*args)

    def shutdown(self):
        pass


@pytest.fixture
def parts():
    return dict(
        llm=FakeLLM(), web=FakeWeb(), launcher=FakeLauncher(),
        memory=FakeMemory(), context=FakeContext(), worker=InlineWorker(), skills=False,
    )


def ask(parts, text, on_status=None):
    brain = TorqueBrain(**parts)
    return brain.process([{"role": "user", "content": text}], on_status=on_status)


def test_open_command(parts):
    assert ask(parts, "Open Chrome.") == "Opening Chrome."
    assert parts["launcher"].opened == ["chrome"]
    assert parts["llm"].calls == []


def test_open_sequence_and_correction(parts):
    assert ask(parts, "open chrome and then open discord") == "Opening Chrome. Opening Discord."
    assert ask(parts, "open edge actually open chrome") == "Opening Chrome."


def test_explicit_open_of_unknown_app_says_so(parts):
    assert "couldn't find" in ask(parts, "open the door")


def test_weak_verb_without_app_falls_through_to_chat(parts):
    assert ask(parts, "start talking to me about python") == "LLM reply"
    assert ask(parts, "quit smoking tips") == "LLM reply"
    assert parts["launcher"].opened == []


def test_close_command(parts):
    assert ask(parts, "close discord") == "Closing Discord."
    assert parts["launcher"].closed == ["discord"]


def test_web_search_announces_and_speaks_clean_text(parts):
    statuses = []
    reply = ask(parts, "what's the weather in toronto", on_status=lambda s, m: statuses.append((s, m)))
    assert statuses == [("searching", "Searching the web...")]
    assert reply.startswith("Let me check the latest weather.")
    assert parts["web"].queries == ["what's the weather in toronto"]
    assert "*" not in reply and "http" not in reply
    assert parts["llm"].calls == []


def test_web_disabled_does_not_announce(parts):
    parts["web"] = FakeWeb(enabled=False)
    statuses = []
    ask(parts, "what's the weather", on_status=lambda s, m: statuses.append(s))
    assert statuses == []


def test_normal_chat_uses_llm_with_original_casing(parts):
    assert ask(parts, "Explain TCP versus UDP, actually simply") == "LLM reply"
    sent = parts["llm"].calls[0][-1]["content"]
    assert sent == "Explain TCP versus UDP, actually simply"


def test_time_and_date_are_answered_locally(parts):
    assert ask(parts, "what time is it").startswith("It's ")
    assert ask(parts, "what's the date today").startswith("Today is ")
    assert parts["llm"].calls == [] and parts["web"].queries == []


def test_streaming_yields_whole_sentences_in_order(parts):
    parts["llm"] = FakeLLM("Python is a language. It is easy to learn. Try it today.")
    brain = TorqueBrain(**parts)
    sentences = list(brain.process_stream([{"role": "user", "content": "tell me about python"}]))
    assert " ".join(sentences) == "Python is a language. It is easy to learn. Try it today."
    assert len(sentences) >= 2


def test_acknowledgements_get_no_reply(parts):
    assert ask(parts, "okay") is None
    assert parts["llm"].calls == []


def test_memory_extraction_only_for_personal_statements(parts):
    ask(parts, "my laptop has 32 gigs of ram")
    ask(parts, "tell me a joke")
    assert parts["memory"].extracted == ["my laptop has 32 gigs of ram"]


def test_llm_down_gives_helpful_message(parts):
    parts["llm"] = FakeLLM(OllamaUnavailableError("refused"))
    assert "Ollama" in ask(parts, "tell me a joke")
