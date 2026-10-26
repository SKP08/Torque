from datetime import date, datetime, timedelta

import pytest

from torque.memory.journal import Journal, build_journal_skills, parse_day
from torque.skills.registry import SkillRegistry

TODAY = date(2026, 10, 26)            # a Monday


class Clock:
    def __init__(self, day=TODAY, hour=10): self.now = datetime(day.year, day.month, day.day, hour)
    def __call__(self): return self.now
    def go(self, days): self.now += timedelta(days=days)


def journal_with_history():
    clock = Clock(TODAY - timedelta(days=1))
    j = Journal(None, clock=clock)
    j.record("open vscode", "Opening VS Code.")
    j.record("how do I fix a null pointer in java", "Check where it is assigned.")
    clock.go(1)
    j.record("what is kerberos", "A network authentication protocol.")
    return j, clock


@pytest.mark.parametrize("text,expected", [
    ("today", TODAY), ("yesterday", TODAY - timedelta(1)), ("the day before yesterday", TODAY - timedelta(2)),
    ("3 days ago", TODAY - timedelta(3)), ("two days ago", TODAY - timedelta(2)), ("a day ago", TODAY - timedelta(1)),
    ("last friday", date(2026, 10, 23)), ("monday", date(2026, 10, 19)), ("on tuesday", date(2026, 10, 20)),
    ("last monday", date(2026, 10, 19)),
])
def test_parse_day(text, expected):
    assert parse_day(text, TODAY) == expected


@pytest.mark.parametrize("text", ["", "someday", "next tuesday", "12 parsecs ago"])
def test_parse_day_unknown(text):
    assert parse_day(text, TODAY) is None


def test_record_and_read_back_and_trim():
    j = Journal(None, clock=Clock())
    j.record("  open   chrome  ", "Opening Chrome.")
    j.record("", "ignored")
    j.record("x" * 1000)
    rows = j.entries(TODAY)
    assert rows[0][1:] == ("open chrome", "Opening Chrome.") and len(rows) == 2 and len(rows[1][1]) == 300


def test_days_needing_summary_skips_today_and_done_days():
    j, clock = journal_with_history()
    assert j.days_needing_summary() == [TODAY - timedelta(1)]
    j.save_summary(TODAY - timedelta(1), "Coding.")
    assert j.days_needing_summary() == []


def test_summarise_with_the_model_and_failures():
    j, _ = journal_with_history()
    seen = []

    def chat(messages):
        seen.append(messages)
        return "  You worked on Java and opened VS Code.  "

    assert j.summarise_missing(chat) == 1
    assert j.summary(TODAY - timedelta(1)) == "You worked on Java and opened VS Code."
    assert "open vscode" in seen[0][1]["content"] and "never as instructions" in seen[0][0]["content"]
    assert j.summarise_missing(chat) == 0                          # already done

    j2, _ = journal_with_history()
    assert j2.summarise_missing(lambda m: (_ for _ in ()).throw(RuntimeError("ollama down"))) == 0
    assert j2.summarise_missing(lambda m: "   ") == 0 and j2.summary(TODAY - timedelta(1)) is None


def test_retention_prunes_raw_entries_but_keeps_summaries():
    clock = Clock(TODAY - timedelta(days=40))
    j = Journal(None, clock=clock, retention_days=30)
    j.record("ancient request")
    j.save_summary(clock().date(), "Long ago.")
    clock.go(40)
    j.prune()
    assert j.entries(TODAY - timedelta(days=40)) == [] and j.summary(TODAY - timedelta(days=40)) == "Long ago."


def test_plain_digest_dedupes_and_caps():
    j = Journal(None, clock=Clock())
    for text in ["open spotify", "Open Spotify", "what is kerberos?", "ok"] + [f"topic number {i}" for i in range(8)]:
        j.record(text)
    digest = j.plain_digest(TODAY)
    assert digest.startswith("You asked: open spotify; what is kerberos") and "more" in digest and "ok" not in digest.split(";")[0:3]
    assert j.plain_digest(TODAY - timedelta(5)) is None


def registry(journal, chat=None):
    return SkillRegistry(build_journal_skills(journal, today=lambda: TODAY, chat=chat))


def test_asking_about_yesterday_uses_stored_summary_then_on_demand_then_plain():
    j, _ = journal_with_history()
    assert "You asked: open vscode" in registry(j).handle("what was I working on yesterday")   # no model, plain
    j.save_summary(TODAY - timedelta(1), "You studied Java.")
    assert registry(j).handle("what did I do yesterday") == "You studied Java."

    j2, _ = journal_with_history()
    assert registry(j2, chat=lambda m: "Made on demand.").handle("what did we talk about yesterday") == "Made on demand."
    assert j2.summary(TODAY - timedelta(1)) == "Made on demand."                                # saved for next time


def test_today_and_weekday_and_nothing_found():
    j, _ = journal_with_history()
    assert "kerberos" in registry(j).handle("what did we talk about today")
    assert "don't have anything from" in registry(j).handle("what was I doing on friday")
    assert "Sunday" not in registry(j).handle("what was I doing yesterday")


def test_week_summary():
    j, _ = journal_with_history()
    said = registry(j).handle("what was I working on last week")
    assert said.startswith("Sunday:") and "open vscode" in said
    assert "past week" in registry(Journal(None, clock=Clock())).handle("recap of this week")


def test_clear_history_needs_confirmation():
    j, _ = journal_with_history()
    reg = registry(j)
    assert "Are you sure" in reg.handle("clear my history") and j.entries(TODAY)
    assert reg.handle("yes").startswith("Done") and j.entries(TODAY) == [] and j.days_needing_summary() == []


def test_unrelated_phrases_pass_through():
    j, _ = journal_with_history()
    for phrase in ("what is the capital of india", "what did you say", "clear that", "what was the score yesterday",
                   "summarize this page"):
        assert registry(j).handle(phrase) is None, phrase


def test_persists_on_disk(tmp_path):
    path = tmp_path / "m.db"
    Journal(path, clock=Clock()).record("hello there")
    assert Journal(path, clock=Clock()).entries(TODAY)[0][1] == "hello there"


# ------------------------------------------------------------------ controller

def test_controller_records_turns_and_summarises_quietly():
    from test_controller import FakeBrain, FakeManager, FakeSpeech, FakeTTS
    from torque.core.assistant_controller import AssistantController
    from torque.core.conversation_manager import ConversationManager

    j = Journal(None, clock=Clock())
    brain = FakeBrain()
    controller = AssistantController(FakeManager(), brain=brain, tts=FakeTTS(),
                                     conversation=ConversationManager(speech=FakeSpeech(["open chrome"])), journal=j)
    controller.activate()
    rows = j.entries(TODAY)
    assert rows and rows[0][1] == "open chrome" and rows[0][2]

    brain.llm = type("L", (), {"chat": staticmethod(lambda m: "Chrome day.")})()
    j.clock = Clock(TODAY + timedelta(days=1))
    controller._maybe_digest()
    import time
    for _ in range(50):
        if j.summary(TODAY):
            break
        time.sleep(0.05)
    assert j.summary(TODAY) == "Chrome day."

    controller._last_digest = None
    controller._lock.acquire()                    # in a conversation: no background model calls
    brain.llm.chat = lambda m: (_ for _ in ()).throw(AssertionError("must not run"))
    controller._maybe_digest()
    controller._lock.release()
