import json

import pytest

from torque.alerts.monitors import AlertMonitor
from torque.alerts.watcher import AlertWatcher, timer_message
from torque.skills.registry import SkillRegistry
from torque.skills.timer_skills import build_timer_skills
from torque.timers.store import TimerStore, parse_duration, spoken_duration


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t


@pytest.mark.parametrize("text,seconds", [
    ("5 minutes", 300), ("five minutes", 300), ("an hour", 3600), ("half an hour", 1800),
    ("an hour and a half", 5400), ("1 hour 30 minutes", 5400), ("90 seconds", 90),
    ("1.5 hours", 5400), ("two hours", 7200), ("ten min", 600), ("one and a half hours", 5400),
    ("2 hours and a half", 9000), ("a minute", 60), ("30 sec", 30),
])
def test_parse_duration(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "soon", "nothing", "tomorrow", None])
def test_parse_duration_rejects_non_durations(text):
    assert parse_duration(text) is None


def test_duration_is_capped_at_a_day():
    assert parse_duration("500 hours") == 24 * 3600


def test_spoken_duration():
    assert spoken_duration(1) == "1 second"
    assert spoken_duration(90) == "1 minute and 30 seconds"
    assert spoken_duration(3600) == "1 hour"
    assert spoken_duration(5400) == "1 hour and 30 minutes"


def test_store_due_order_and_persistence(tmp_path):
    clock = Clock()
    path = tmp_path / "t.json"
    store = TimerStore(path, clock)
    store.add(60, "pasta")
    store.add(10, "call mom", "reminder")

    assert [i["label"] for i in store.active()] == ["call mom", "pasta"]
    assert store.pop_due() == []

    # a restart keeps them
    again = TimerStore(path, clock)
    assert len(again.active()) == 2

    clock.t += 30
    due = again.pop_due()
    assert [i["label"] for i in due] == ["call mom"]
    assert [i["label"] for i in again.active()] == ["pasta"]
    assert len(json.loads(path.read_text())) == 1


def test_timer_that_came_due_while_torque_was_off_fires_on_start(tmp_path):
    clock = Clock()
    path = tmp_path / "t.json"
    TimerStore(path, clock).add(5, "tea")
    clock.t += 3600
    assert [i["label"] for i in TimerStore(path, clock).pop_due()] == ["tea"]


def test_corrupt_file_is_ignored(tmp_path):
    path = tmp_path / "t.json"
    path.write_text("{not json")
    assert TimerStore(path).active() == []


def test_cancel(tmp_path):
    store = TimerStore(None, Clock())
    store.add(5)
    store.add(5, "x", "reminder")
    assert store.cancel() == 2 and store.active() == []
    assert store.cancel() == 0


def make_registry():
    store = TimerStore(None, Clock())
    return SkillRegistry(build_timer_skills(store)), store


@pytest.mark.parametrize("phrase,label,seconds,kind", [
    ("Set a timer for 5 minutes", "", 300, "timer"),
    ("set a pasta timer for ten minutes", "pasta", 600, "timer"),
    ("timer for half an hour", "", 1800, "timer"),
    ("start a timer of 90 seconds", "", 90, "timer"),
    ("remind me in 20 minutes to call mom", "call mom", 1200, "reminder"),
    ("remind me to check the oven in the kitchen in 5 minutes", "check the oven in the kitchen", 300, "reminder"),
    ("hey torque remind me to stretch in an hour and a half", "stretch", 5400, "reminder"),
])
def test_setting_timers_by_voice(phrase, label, seconds, kind):
    registry, store = make_registry()
    assert registry.handle(phrase), phrase
    (item,) = store.active()
    assert (item["label"], item["seconds"], item["kind"]) == (label, seconds, kind)


def test_status_and_cancel_by_voice():
    registry, store = make_registry()
    assert "no timers" in registry.handle("what are my timers")
    registry.handle("set a tea timer for 3 minutes")
    assert "tea" in registry.handle("what are my timers")
    assert registry.handle("cancel the timer") == "Cancelled." and store.active() == []
    assert "nothing" in registry.handle("cancel my timers")


def test_unrelated_phrases_fall_through():
    registry, _ = make_registry()
    for text in ("stop", "what time is it", "open spotify", "tell me about timers in c"):
        assert registry.handle(text) is None, text


def test_timer_without_duration_asks():
    registry, store = make_registry()
    assert registry.handle("set a timer for a while") is None
    assert registry.handle("set a timer for") is None
    assert store.active() == []


def test_messages():
    assert timer_message({"kind": "timer", "label": ""}) == "Your timer is up."
    assert timer_message({"kind": "timer", "label": "pasta"}) == "Your pasta timer is up."
    assert timer_message({"kind": "reminder", "label": "call mom"}) == "Reminder: call mom."


def test_watcher_announces_due_timers_once():
    clock = Clock()
    store = TimerStore(None, clock)
    store.add(5, "pasta")
    heard = []
    watcher = AlertWatcher(store, lambda m, s, sp: heard.append(m), clock=clock)

    assert watcher.tick() == 0
    clock.t += 6
    assert watcher.tick() == 1 and watcher.tick() == 0
    assert heard == ["Your pasta timer is up."]


# ---- monitors ----

def status(cpu=10, memory=40, disk=50, battery=None, top=None):
    return {"cpu": cpu, "memory": memory, "disk": disk, "battery": battery, "top": top or []}


def monitor(seq, ports=None, clock=None, **kw):
    it = iter(seq)
    last = {"v": None}

    def fn():
        try:
            last["v"] = next(it)
        except StopIteration:
            pass
        return last["v"]

    return AlertMonitor(fn, ports, clock=clock or Clock(), **kw)


def test_battery_low_alert_not_when_plugged_and_cooldown():
    clock = Clock()
    m = monitor([status(battery={"percent": 15, "plugged": True}),
                 status(battery={"percent": 15, "plugged": False})] * 3, clock=clock)
    assert m.check() == []
    first = m.check()
    assert len(first) == 1 and first[0].category == "battery" and "15" in first[0].message
    assert m.check() == []                      # cooldown
    clock.t += 1000
    assert len(m.check()) == 1                  # cooldown over, still low -> told again


def test_battery_critical_escalates():
    clock = Clock()
    m = monitor([status(battery={"percent": 18, "plugged": False}),
                 status(battery={"percent": 6, "plugged": False})], clock=clock)
    assert m.check()[0].severity == "info"
    critical = m.check()
    assert critical and critical[0].severity == "warn" and "critically" in critical[0].message


def test_cpu_must_be_sustained():
    m = monitor([status(cpu=95, top=[{"name": "miner.exe", "cpu": 90}]), status(cpu=95), status(cpu=20),
                 status(cpu=95), status(cpu=95), status(cpu=95)])
    assert [m.check() for _ in range(3)] == [[], [], []]           # spike broken by a calm sample
    assert m.check() == [] and m.check() == []
    alerts = m.check()
    assert len(alerts) == 1 and alerts[0].category == "cpu"


def test_cpu_alert_names_busiest_process():
    m = monitor([status(cpu=99, top=[{"name": "miner.exe", "cpu": 90}])] * 3)
    m.check(); m.check()
    assert "miner.exe" in m.check()[0].message


def test_disk_alert_and_category_toggle():
    m = monitor([status(disk=97)] * 4)
    assert m.check()[0].category == "disk"
    off = monitor([status(disk=97, battery={"percent": 3, "plugged": False})] * 3, categories=["cpu"])
    assert off.check() == []


def test_new_exposed_port_is_reported_once_after_baseline():
    ports = [[(135, "svchost.exe", True)]]
    m = monitor([status()] * 5, lambda: ports[0])
    assert m.check() == []                                         # baseline
    assert m.check() == []
    ports[0] = [(135, "svchost.exe", True), (4444, "nc.exe", True), (8000, "python.exe", False)]
    alerts = m.check()
    assert len(alerts) == 1 and "nc.exe" in alerts[0].message and "4444" in alerts[0].message
    assert m.check() == []                                         # once only


def test_monitor_survives_broken_probes():
    def boom():
        raise RuntimeError("x")

    assert AlertMonitor(boom, boom).check() == []


def test_watcher_runs_monitor_on_its_own_interval():
    clock = Clock()
    seen = []
    m = monitor([status(disk=99)] * 10, clock=clock)
    watcher = AlertWatcher(TimerStore(None, clock), lambda msg, sev, sp: seen.append(msg),
                           m, monitor_every=20, clock=clock)
    assert watcher.tick() == 1
    assert watcher.tick() == 0                                     # not due yet
    clock.t += 21
    watcher.tick()                                                 # monitor ran again; disk on cooldown
    assert len(seen) == 1


# ---- controller ----

def _controller(tts_spoken, sent):
    from test_controller import FakeBrain, FakeSpeech
    from torque.core.assistant_controller import AssistantController
    from torque.core.conversation_manager import ConversationManager

    class WS:
        def set_message_handler(self, h): pass
        def send(self, data): sent.append(data)
        def send_level(self, x): pass

    ws = WS()

    class Manager:
        def get(self, _): return ws

    class TTS:
        def speak(self, text): tts_spoken.append(text)

    return AssistantController(Manager(), brain=FakeBrain(), tts=TTS(),
                               conversation=ConversationManager(speech=FakeSpeech([])))


def test_alert_is_spoken_when_idle_and_shown_as_toast():
    spoken, sent = [], []
    c = _controller(spoken, sent)
    c.announce("Your timer is up.", "info")
    assert spoken == ["Your timer is up."]
    toast = next(m["hud"] for m in sent if m.get("hud"))
    assert toast["kind"] == "alert" and toast["message"] == "Your timer is up." and toast["hold"] == 8


def test_alert_waits_for_the_conversation_to_finish():
    spoken, sent = [], []
    c = _controller(spoken, sent)
    c._lock.acquire()                                # a conversation is running
    c.announce("Battery is at 15 percent.", "info")
    assert spoken == []                              # not interrupted...
    assert any(m.get("hud") for m in sent)           # ...but visible
    c._lock.release()
    c._flush_speech()
    assert spoken == ["Battery is at 15 percent."]


def test_alert_speech_can_be_switched_off():
    spoken, sent = [], []
    c = _controller(spoken, sent)
    c.config["alert_speech"] = False
    c.announce("x")
    assert spoken == []
