import asyncio
import json
import urllib.error
import urllib.request

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from torque.phone.phone_server import AuthGuard, PhoneServer, load_or_create_token
from torque.skills.pc_control import build_pc_skills
from torque.skills.registry import SkillRegistry

from test_skills import FakeBackend, make_brain, say

TOKEN = "t" * 32


@pytest.fixture
def server():
    asked = []

    def ask(text):
        asked.append(text)
        return f"reply to {text}"

    s = PhoneServer(ask, TOKEN, host="127.0.0.1", port=0)
    assert s.start()
    s.asked = asked
    yield s
    s.stop()


def run(coro):
    return asyncio.run(coro)


async def authed(server):
    ws = await connect(f"ws://127.0.0.1:{server.port}")
    await ws.send(json.dumps({"type": "auth", "token": TOKEN}))
    assert json.loads(await ws.recv()) == {"type": "auth", "ok": True}
    return ws


def test_page_is_served_with_a_strict_csp(server):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=3) as r:
        body = r.read().decode()
        assert r.status == 200 and "<title>Torque</title>" in body
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
        assert r.headers["Cache-Control"] == "no-store"


def test_page_never_contains_the_token(server):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=3) as r:
        assert TOKEN not in r.read().decode()


def test_other_paths_are_404(server):
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/data/phone_token.txt", timeout=3)
    assert error.value.code == 404


def test_authenticated_request_gets_a_reply(server):
    async def go():
        ws = await authed(server)
        await ws.send(json.dumps({"type": "text", "id": 7, "text": "what time is it"}))
        return json.loads(await ws.recv())
    assert run(go()) == {"type": "reply", "id": 7, "text": "reply to what time is it"}


def test_wrong_token_is_rejected_and_nothing_runs(server):
    async def go():
        ws = await connect(f"ws://127.0.0.1:{server.port}")
        await ws.send(json.dumps({"type": "auth", "token": "wrong"}))
        with pytest.raises(ConnectionClosed) as closed:
            await ws.recv()
        return closed.value.rcvd.code
    assert run(go()) == 4401
    assert server.asked == []


def test_sending_a_command_without_authenticating_does_not_run_it(server):
    async def go():
        ws = await connect(f"ws://127.0.0.1:{server.port}")
        await ws.send(json.dumps({"type": "text", "id": 1, "text": "lock my computer"}))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
    run(go())
    assert server.asked == []


@pytest.mark.parametrize("bad", [123, None, ["x"], {"a": 1}, ""])
def test_non_string_tokens_are_rejected(server, bad):
    async def go():
        ws = await connect(f"ws://127.0.0.1:{server.port}")
        await ws.send(json.dumps({"type": "auth", "token": bad}))
        with pytest.raises(ConnectionClosed):
            await ws.recv()
    run(go())


def test_repeated_failures_lock_the_address_out(server):
    async def attempt(token="nope"):
        ws = await connect(f"ws://127.0.0.1:{server.port}")
        try:
            await ws.send(json.dumps({"type": "auth", "token": token}))
        except ConnectionClosed:
            pass                      # already closed by the lockout
        with pytest.raises(ConnectionClosed) as closed:
            await ws.recv()
        return closed.value.rcvd.code

    async def go():
        return [await attempt() for _ in range(6)]

    codes = run(go())
    assert codes[:5] == [4401] * 5 and codes[5] == 4429

    assert run(attempt(TOKEN)) == 4429          # even the right token, while locked out


def test_oversize_and_empty_text_are_refused(server):
    async def go():
        ws = await authed(server)
        out = []
        for text in ["", "x" * 501]:
            await ws.send(json.dumps({"type": "text", "id": 1, "text": text}))
            out.append(json.loads(await ws.recv())["type"])
        return out
    assert run(go()) == ["error", "error"]
    assert server.asked == []


def test_garbage_messages_do_not_crash_the_connection(server):
    async def go():
        ws = await authed(server)
        await ws.send("not json")
        assert json.loads(await ws.recv())["type"] == "error"
        await ws.send(json.dumps({"type": "text", "id": 2, "text": "hi"}))
        return json.loads(await ws.recv())["text"]
    assert run(go()) == "reply to hi"


def test_auth_guard_expires_lockout():
    class Clock:
        t = 0.0
        def __call__(self): return self.t
    clock = Clock()
    guard = AuthGuard(clock)
    for _ in range(5):
        guard.failed("1.2.3.4")
    assert guard.locked("1.2.3.4") and not guard.locked("5.6.7.8")
    clock.t = 301
    assert not guard.locked("1.2.3.4")


def test_token_is_created_once_and_reused(tmp_path):
    path = tmp_path / "data" / "phone_token.txt"
    first = load_or_create_token(path)
    assert len(first) >= 30 and load_or_create_token(path) == first
    path.unlink()
    assert load_or_create_token(path) != first          # delete to rotate


# ---- what a phone is allowed to do ---------------------------------------

def remote(brain, text):
    return " ".join(brain.process_stream([{"role": "user", "content": text}], remote=True))


def test_phone_cannot_trigger_power_actions():
    backend = FakeBackend()
    brain = make_brain(SkillRegistry(build_pc_skills(backend)))
    assert remote(brain, "shut down the computer") == "That one needs you at the PC."
    assert backend.calls == [] and not brain.awaiting_confirmation


def test_phone_cannot_confirm_a_power_action_pending_at_the_pc():
    backend = FakeBackend()
    brain = make_brain(SkillRegistry(build_pc_skills(backend)))
    assert "Say yes" in say(brain, "restart the computer")          # at the PC
    remote(brain, "yes")                                              # from the phone
    assert ("restart",) not in backend.calls
    assert say(brain, "yes") == "Restarting."                         # still pending for the PC


def test_phone_can_still_use_safe_skills():
    backend = FakeBackend()
    brain = make_brain(SkillRegistry(build_pc_skills(backend)))
    assert remote(brain, "take a screenshot").startswith("Screenshot saved")
