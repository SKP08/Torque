import pytest

from torque.alerts.monitors import AlertMonitor
from torque.security import persistence as p
from torque.skills.registry import SkillRegistry
from torque.skills.security import build_security_skills


class Clock:
    t = 0.0
    def __call__(self): return self.t


class Probe:
    def __init__(self, procs=()): self._p = list(procs)
    def processes(self): return self._p


def make(tmp_path, startup, hosts, clock=None):
    state = {"startup": dict(startup), "hosts": list(hosts)}
    watch = p.PersistenceWatch(tmp_path / "b.json", {"startup": lambda: state["startup"], "hosts": lambda: state["hosts"]},
                               every=300, clock=clock or Clock())
    return watch, state


def test_first_look_is_a_silent_baseline_then_changes_alert_once(tmp_path):
    clock = Clock()
    watch, state = make(tmp_path, {"HKCU Run: OneDrive": "od.exe"}, ["127.0.0.1 ads.example.com"], clock)
    assert watch.check() == []

    clock.t = 100
    state["startup"]["HKCU Run: Updater"] = "C:/Users/x/AppData/Local/Temp/u.exe"
    assert watch.check() == []                       # not due yet (every 300 s)

    clock.t = 400
    alerts = watch.check()
    assert len(alerts) == 1 and "Updater" in alerts[0].message and alerts[0].severity == "warn"
    clock.t = 800
    assert watch.check() == []                       # reported once


def test_hosts_redirect_is_flagged_and_removal_is_not(tmp_path):
    clock = Clock()
    watch, state = make(tmp_path, {}, ["127.0.0.1 ads.example.com"], clock)
    watch.check()
    clock.t = 400
    state["hosts"].append("6.6.6.6 paypal.com")
    alert = watch.check()[0]
    assert "paypal.com" in alert.message and "6.6.6.6" in alert.message
    clock.t = 800
    state["hosts"].clear()
    assert watch.check() == []


def test_baseline_survives_restart_so_offline_changes_are_caught(tmp_path):
    watch, state = make(tmp_path, {"a": "1"}, [])
    watch.check()
    state["startup"]["evil"] = "x"
    again = p.PersistenceWatch(tmp_path / "b.json", {"startup": lambda: state["startup"], "hosts": lambda: []}, clock=Clock())
    assert again.baseline["startup"] == {"a": "1"}
    assert "evil" in again.check()[0].message


def test_failing_source_and_corrupt_baseline_do_not_crash(tmp_path):
    (tmp_path / "b.json").write_text("{nope")
    def boom(): raise RuntimeError("registry locked")
    watch = p.PersistenceWatch(tmp_path / "b.json", {"startup": boom, "hosts": lambda: []}, clock=Clock())
    assert watch.baseline is None and watch.check() == []


def test_monitor_runs_extra_checks_and_survives_their_errors(tmp_path):
    watch, state = make(tmp_path, {}, [])
    def bad(): raise RuntimeError
    monitor = AlertMonitor(lambda: None, extra=[bad, watch.check])
    assert monitor.check() == []


def test_hosts_file_parsing(tmp_path):
    f = tmp_path / "hosts"
    f.write_text("# comment\n127.0.0.1   localhost\n\n  0.0.0.0 ads.example.com  # blocked\n127.0.0.1 localhost\n")
    assert p.hosts_lines(f) == ["0.0.0.0 ads.example.com", "127.0.0.1 localhost"]
    assert p.hosts_lines(tmp_path / "missing") == []
    assert "blocks a site" in p.hosts_concern("0.0.0.0 ads.example.com")
    assert "fake site" in p.hosts_concern("6.6.6.6 google.com")
    assert "fake site" in p.hosts_concern("127.0.0.1 paypal.com")


def skills(tmp_path, procs=(), startup=None, hosts=()):
    watch, state = make(tmp_path, startup or {}, hosts)
    return SkillRegistry(build_security_skills(Probe(procs), watch=watch)), watch, state


def test_startup_and_hosts_by_voice(tmp_path):
    reg, watch, state = skills(tmp_path, startup={"HKCU Run: OneDrive": "x", "HKCU Run: Spotify": "y"}, hosts=["6.6.6.6 paypal.com"])
    watch.check()
    said = reg.handle("what's in my startup")
    assert "2 things start with your PC" in said and "Nothing new" in said
    state["startup"]["HKCU Run: Sneaky"] = "z"
    assert "New since I first looked: Sneaky" in reg.handle("check my startup programs")
    assert "suspicious" in reg.handle("has my hosts file been changed")


def test_explain_process(tmp_path):
    procs = [("svchost.exe", "C:/Users/me/Downloads/svchost.exe"), ("ollama.exe", "C:/ollama.exe"), ("weird.exe", "C:/Games/weird.exe")]
    reg, *_ = skills(tmp_path, procs)
    assert "classic disguise" in reg.handle("explain the process svchost") or "downloads folder" in reg.handle("explain the process svchost")
    assert "local AI model server" in reg.handle("what is ollama.exe")
    assert "do not recognise" in reg.handle("is weird.exe safe")
    assert "don't see" in reg.handle("is nothere.exe safe")


@pytest.mark.parametrize("phrase", ["what is the capital of india", "what is python", "what is a firewall", "explain recursion",
                                    "is it safe to travel to japan", "tell me about the moon", "what is chrome"])
def test_explain_process_does_not_hijack_normal_questions(tmp_path, phrase):
    reg, *_ = skills(tmp_path)
    assert reg.handle(phrase) is None


@pytest.mark.parametrize("phrase", ["is it safe", "is this safe", "is that dangerous", "are they safe", "is water safe"])
def test_pronouns_are_not_process_names(tmp_path, phrase):
    reg, *_ = skills(tmp_path)
    assert reg.handle(phrase) is None
