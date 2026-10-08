import asyncio
import json
import threading

from websockets.server import serve
from loguru import logger

from torque.system.service import Service


class WebSocketService(Service):

    def __init__(self):
        self.clients = set()
        self.loop = None

    @property
    def name(self):
        return "WebSocket Service"

    def initialize(self):
        self.loop = asyncio.new_event_loop()

        threading.Thread(
            target=self._run_loop,
            daemon=True,
        ).start()

        logger.info("WebSocket server started on ws://localhost:8765")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._start_server())
        self.loop.run_forever()

    async def _start_server(self):
        await serve(self._handler, "localhost", 8765)

    async def _handler(self, websocket):
        logger.success("UI Connected")

        self.clients.add(websocket)

        try:
            async for _ in websocket:
                pass

        finally:
            self.clients.remove(websocket)
            logger.warning("UI Disconnected")

    def send(self, data):

        if not self.clients:
            return

        asyncio.run_coroutine_threadsafe(
            self._broadcast(data),
            self.loop,
        )

    async def _broadcast(self, data):

        message = json.dumps(data)

        for client in list(self.clients):

            try:
                await client.send(message)

            except:
                self.clients.remove(client)