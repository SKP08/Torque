import pytest

from torque.skills.registry import SkillRegistry
from torque.skills.security import (
    PsutilProbe, build_security_skills, describe_ports, find_suspicious,
)
from collections import Counter


class FakeProbe:
    def __init__(self, **kw):
        self.ports = kw.get("ports", [])
        self.conns = kw.get("conns", Counter())
        self.top = kw.get("top", [])
        self.procs = kw.get("procs", [])
        self.devices = kw.get("devices", [])

    def listening_ports(self): return self.ports
    def connections_by_process(self): return self.conns
    def top_processes(self, by="cpu", count=3): return self.top
    def processes(self): return self.procs
    def network_devices(self): return self.devices


def ask(probe, text):
    return SkillRegistry(build_security_skills(probe)).handle(text)


def test_exposed_ports_are_called_out():
    probe = FakeProbe(ports=[(80, "nginx.exe", True), (5432, "postgres.exe", False), (8765, "python.exe", False)])
    reply = ask(probe, "what ports are open on my pc")
    assert "1 port reachable from your network: nginx.exe on port 80" in reply
    assert "2 others are local only" in reply


def test_all_local_ports_reassure():
    reply = describe_ports(FakeProbe(ports=[(8765, "python.exe", False)]))
    assert "Nothing is exposed" in reply


def test_no_ports():
    assert "Nothing is listening" in ask(FakeProbe(), "open ports")


def test_network_use():
    probe = FakeProbe(conns=Counter({"chrome.exe": 12, "discord.exe": 3}))
    reply = ask(probe, "what's using my network")
    assert reply.startswith("Most connections: chrome.exe with 12 connections")


def test_cpu_and_memory():
    probe = FakeProbe(top=[("chrome.exe", 31.2), ("code.exe", 8.0)])
    assert "chrome.exe, 31 percent" in ask(probe, "what is using my cpu")
    assert "processor" in ask(probe, "what's slowing down my computer")
    assert "memory" in ask(probe, "what's using my ram")


def test_suspicious_heuristics():
    procs = [
        ("chrome.exe", r"C:\Program Files\Google\Chrome\chrome.exe"),
        ("svchost.exe", r"C:\Windows\System32\svchost.exe"),
        ("svchost.exe", r"C:\Users\me\AppData\Local\Temp\svchost.exe"),
        ("setup.exe", r"C:\Users\me\Downloads\setup.exe"),
    ]
    found = find_suspicious(FakeProbe(procs=procs))
    names = [n for n, _ in found]
    assert "chrome.exe" not in names
    assert ("svchost.exe", "running from a temporary or downloads folder") in found
    assert ("setup.exe", "running from a temporary or downloads folder") in found
    assert len(found) == 2          # the real svchost is not flagged


def test_system_name_outside_windows_folder_is_flagged():
    found = find_suspicious(FakeProbe(procs=[("lsass.exe", r"D:\tools\lsass.exe")]))
    assert "system name" in found[0][1]


def test_clean_machine_is_not_overclaimed():
    reply = ask(FakeProbe(procs=[("a.exe", r"C:\Program Files\a.exe")]), "anything suspicious running")
    assert "not a full malware scan" in reply


def test_findings_are_hedged():
    reply = ask(FakeProbe(procs=[("x.exe", r"C:\Temp\x.exe")]), "check for suspicious processes")
    assert "not proof" in reply


def test_devices():
    assert "2 devices" in ask(FakeProbe(devices=[("192.168.1.2", "aa"), ("192.168.1.3", "bb")]), "who's on my wifi")
    assert "can't see" in ask(FakeProbe(), "who is on my network")


@pytest.mark.parametrize("text", [
    "what is the open ports protocol", "tell me about network security",
    "how do ports work", "what is suspicious behaviour", "who is on first",
])
def test_conversation_is_not_hijacked(text):
    assert ask(FakeProbe(), text) is None


def test_real_probe_runs_on_this_machine():
    probe = PsutilProbe()
    assert isinstance(probe.listening_ports(), list)
    assert isinstance(probe.top_processes("memory", 2), list)
    assert isinstance(probe.processes(), list)
    assert isinstance(probe.network_devices(), list)
