import asyncio
import json
import threading

from loguru import logger
from websockets.asyncio.server import broadcast, serve
from websockets.exceptions import ConnectionClosed

from torque.system.config_service import load_config
from torque.system.service import Service

# Origins allowed to connect from a browser. Browsers always send an Origin
# header on WebSocket handshakes, so this stops arbitrary web pages from
# reading Torque's output. `None` allows non-browser clients (no Origin).
DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    None,
]

MAX_MESSAGE_BYTES = 64 * 1024


class WebSocketService(Service):
    """
    Local WebSocket hub between Torque and its UI.

    Outbound: JSON status messages ({"state": ..., "message": ...}) are
    broadcast to every client; a new client immediately receives the latest.

    Inbound: JSON messages with a "type" field are passed to the handler
    registered with set_message_handler().
    """

    def __init__(self, host=None, port=None, origins=None):
        self._host = host
        self._port = port
        self._origins = origins

        self.clients = set()
        self.loop = None
        self.port = None

        self.last_message = None

        self._handler_callback = None
        self._ready = threading.Event()
        self._stop_event = None
        self._thread = None
        self._error = None

    @property
    def name(self):
        return "WebSocket Service"

    # ----------------------------------------------------------
    # LIFECYCLE
    # ----------------------------------------------------------

    def initialize(self):

        config = load_config()

        self.host = self._host or config["ws_host"]
        self.port = self._port if self._port is not None else config["ws_port"]

        if self._origins is not None:
            self.origins = self._origins
        else:
            self.origins = list(DEFAULT_ORIGINS)

            ui_url = config.get("ui_url")

            if ui_url and ui_url not in self.origins:
                self.origins.insert(0, ui_url.rstrip("/"))

        self.loop = asyncio.new_event_loop()

        self._thread = threading.Thread(
            target=self._run_loop,
            name="TorqueWebSocket",
            daemon=True,
        )

        self._thread.start()

        if not self._ready.wait(timeout=5):
            logger.error("WebSocket server did not start in time.")

        elif self._error:
            logger.error(f"WebSocket server failed to start: {self._error}")

        else:
            logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")

    def shutdown(self):

        if self.loop and self._stop_event:
            self.loop.call_soon_threadsafe(self._stop_event.set)

        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self):

        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._serve())

        except Exception as error:  # noqa: BLE001
            self._error = error
            self._ready.set()
            logger.exception("WebSocket server crashed.")

    async def _serve(self):

        self._stop_event = asyncio.Event()

        async with serve(
            self._handler,
            self.host,
            self.port,
            origins=self.origins,
            max_size=MAX_MESSAGE_BYTES,
        ) as server:

            # Port 0 means "pick a free port"; record the real one.
            self.port = server.sockets[0].getsockname()[1]

            self._ready.set()

            await self._stop_event.wait()

    # ----------------------------------------------------------
    # CONNECTIONS
    # ----------------------------------------------------------

    async def _handler(self, websocket):

        logger.success("UI Connected")

        self.clients.add(websocket)

        try:
            if self.last_message:
                await websocket.send(self.last_message)

            async for raw in websocket:
                self._dispatch(raw)

        except ConnectionClosed:
            pass

        finally:
            self.clients.discard(websocket)
            logger.warning("UI Disconnected")

    def _dispatch(self, raw):

        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning("Ignoring non-JSON WebSocket message.")
            return

        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            logger.warning("Ignoring WebSocket message without a 'type'.")
            return

        callback = self._handler_callback

        if callback is None:
            return

        # Never block the event loop with controller work.
        self.loop.run_in_executor(None, self._safe_call, callback, message)

    @staticmethod
    def _safe_call(callback, message):

        try:
            callback(message)
        except Exception:  # noqa: BLE001
            logger.exception("WebSocket message handler failed.")

    def set_message_handler(self, callback):
        self._handler_callback = callback

    # ----------------------------------------------------------
    # OUTBOUND
    # ----------------------------------------------------------

    def send(self, data):
        """Thread-safe broadcast to all connected clients."""

        message = json.dumps(data)

        if isinstance(data, dict) and "state" in data:
            self.last_message = message

        self._broadcast_text(message)

    def send_level(self, level: float):
        """Microphone level for animations. Not replayed to new clients."""

        self._broadcast_text(json.dumps({"level": round(level, 3)}))

    def _broadcast_text(self, message: str):

        if not self.loop or self.loop.is_closed() or not self.clients:
            return

        try:
            self.loop.call_soon_threadsafe(
                broadcast,
                set(self.clients),
                message,
            )
        except RuntimeError:
            pass          # loop closed while shutting down
