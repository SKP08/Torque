import json

import pytest

from torque.push.ntfy import Pusher, build_pusher
from torque.skills.push_skills import build_push_skills
from torque.skills.registry import SkillRegistry


class Net:
    def __init__(self): self.calls = []
    def __call__(self, url, data, headers): self.calls.append((url, data.decode(), headers))


def pusher(net=None, idle=600, **kw):
    t = {"now": 0.0}
    p = Pusher("secret-topic-abc", idle_fn=lambda: idle, post=net or Net(), clock=lambda: t["now"], background=False, **kw)
    p.t = t
    return p


def test_sends_warnings_when_away():
    net = Net()
    p = pusher(net)
    assert p.send("Battery critically low", "warn")
    url, body, headers = net.calls[0]
    assert url == "https://ntfy.sh/secret-topic-abc" and body == "Battery critically low"
    assert headers["Priority"] == "high" and headers["Title"] == "Torque"


def test_not_while_you_are_at_the_pc_and_not_for_info():
    net = Net()
    assert not pusher(net, idle=5).send("x", "warn")
    assert not pusher(net, idle=600).send("Timer done", "info")
    assert pusher(net, idle=5, min_idle=0).send("y", "warn")             # 0 = always
    assert pusher(net, idle=5, levels=("warn", "info")) .send("z", "info", force=True)


def test_duplicates_are_suppressed_for_ten_minutes():
    net = Net()
    p = pusher(net)
    assert p.send("CPU high", "warn") and not p.send("CPU high", "warn")
    p.t["now"] = 700
    assert p.send("CPU high", "warn") and len(net.calls) == 2


def test_disabled_without_topic_or_with_plain_http():
    assert build_pusher({}) is None and build_pusher({"push_enabled": True, "push_topic": ""}) is None
    assert build_pusher({"push_enabled": False, "push_topic": "t"}) is None
    assert not Pusher("t", server="http://insecure.example", background=False, post=Net(), idle_fn=lambda: 999).send("x", "warn")
    assert build_pusher({"push_enabled": True, "push_topic": "t"}).enabled


def test_network_failure_never_raises():
    def boom(*a): raise OSError("offline")
    assert pusher(boom).send("x", "warn")         # started; failure is logged, not raised


def test_idle_probe_failure_means_no_push():
    def bad(): raise RuntimeError
    p = Pusher("t", idle_fn=bad, post=Net(), background=False)
    assert not p.send("x", "warn")


def test_test_alert_skill():
    net = Net()
    reg = SkillRegistry(build_push_skills(pusher(net, idle=0)))
    assert "Sent a test alert" in reg.handle("send a test alert to my phone")
    assert "already sent" in reg.handle("send a test notification to my phone")
    off = SkillRegistry(build_push_skills(None))
    assert "Phone alerts are off" in off.handle("test my phone alerts")
    assert reg.handle("what is the weather") is None


def test_local_settings_override(tmp_path, monkeypatch):
    from torque.system import config_service as cs
    main = tmp_path / "settings.json"
    main.write_text(json.dumps({"push_enabled": False}))
    (tmp_path / "settings.local.json").write_text(json.dumps({"push_enabled": True, "push_topic": "abc"}))
    monkeypatch.setattr(cs, "CONFIG_PATH", main)
    cfg = cs.load_config(force=True)
    assert cfg["push_enabled"] and cfg["push_topic"] == "abc"
    (tmp_path / "settings.local.json").write_text("{bad")
    assert not cs.load_config(force=True)["push_enabled"]
    monkeypatch.undo(); cs.load_config(force=True)
