import asyncio
import json

from websockets.asyncio.client import connect

from torque.conversation.conversation_policy import ConversationPolicy
from torque.core.assistant_controller import AssistantController
from torque.core.conversation_manager import ConversationManager
from torque.system.service_manager import ServiceManager
from torque.websocket.websocket_service import WebSocketService

from test_controller import FakeBrain, FakeSpeech, FakeTTS


def test_text_message_over_websocket_drives_state_updates():
    ws = WebSocketService(host="127.0.0.1", port=0)
    manager = ServiceManager()
    manager.register(ws)
    manager.initialize()

    brain, tts = FakeBrain(), FakeTTS()
    AssistantController(
        manager, brain=brain, tts=tts,
        conversation=ConversationManager(speech=FakeSpeech([])),
    )

    async def go():
        states = []

        async with connect(f"ws://127.0.0.1:{ws.port}", origin="http://localhost:5173") as c:
            states.append(json.loads(await asyncio.wait_for(c.recv(), 2)))   # replay of "idle"
            await c.send(json.dumps({"type": "text", "text": "hello torque"}))

            while states[-1] != {"state": "idle", "message": ""} or len(states) < 4:
                states.append(json.loads(await asyncio.wait_for(c.recv(), 3)))

        return states

    try:
        states = asyncio.run(go())
    finally:
        manager.shutdown()

    assert [s["state"] for s in states] == ["idle", "thinking", "speaking", "idle"]
    assert states[2]["message"] == "reply to hello torque"
    assert tts.spoken == ["reply to hello torque"]
    # Clean shutdown frees the port/thread.
    assert not ws._thread.is_alive()
