import asyncio
import json
import threading
import time

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus

from torque.websocket.websocket_service import WebSocketService

GOOD_ORIGIN = "http://localhost:5173"


@pytest.fixture
def service():
    ws = WebSocketService(host="127.0.0.1", port=0)
    ws.initialize()
    yield ws
    ws.shutdown()


def run(coro):
    return asyncio.run(coro)


def test_new_client_receives_last_state(service):
    service.send({"state": "idle", "message": ""})

    async def go():
        async with connect(f"ws://127.0.0.1:{service.port}", origin=GOOD_ORIGIN) as c:
            return json.loads(await asyncio.wait_for(c.recv(), 2))

    assert run(go()) == {"state": "idle", "message": ""}


def test_broadcast_reaches_connected_client(service):
    async def go():
        async with connect(f"ws://127.0.0.1:{service.port}", origin=GOOD_ORIGIN) as c:
            await asyncio.sleep(0.2)
            service.send({"state": "listening", "message": "Listening..."})
            return json.loads(await asyncio.wait_for(c.recv(), 2))

    assert run(go())["state"] == "listening"


def test_foreign_origin_is_rejected(service):
    async def go():
        async with connect(f"ws://127.0.0.1:{service.port}", origin="http://evil.example"):
            pass

    with pytest.raises(InvalidStatus) as error:
        run(go())

    assert error.value.response.status_code == 403


def test_client_without_origin_is_allowed(service):
    async def go():
        async with connect(f"ws://127.0.0.1:{service.port}") as c:
            await c.send(json.dumps({"type": "ping"}))

    run(go())


def test_inbound_messages_reach_handler_and_bad_ones_are_ignored(service):
    received = []
    done = threading.Event()

    def handler(message):
        received.append(message)
        done.set()

    service.set_message_handler(handler)

    async def go():
        async with connect(f"ws://127.0.0.1:{service.port}", origin=GOOD_ORIGIN) as c:
            await c.send("not json")
            await c.send(json.dumps(["list"]))
            await c.send(json.dumps({"no": "type"}))
            await c.send(json.dumps({"type": "cancel"}))
            await asyncio.sleep(0.3)

    run(go())

    assert done.wait(2)
    assert received == [{"type": "cancel"}]


def test_send_without_clients_is_safe(service):
    service.send({"state": "idle", "message": ""})
    time.sleep(0.05)


def test_overlay_origins_follow_ui_port():
    from torque.websocket.websocket_service import WebSocketService

    service = WebSocketService(port=0)
    service.initialize()
    try:
        assert "http://127.0.0.1:5174" in service.origins
        assert "http://localhost:5174" in service.origins
        assert "http://localhost:5173" in service.origins        # vite dev server
    finally:
        service.shutdown()


def test_level_messages_are_not_replayed_to_new_clients(service):
    service.send({"state": "listening", "message": "Listening..."})
    service.send_level(0.5)
    assert "level" not in service.last_message
