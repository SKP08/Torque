"""
Talk to Torque from your phone.

A small web page plus a WebSocket, both on one port. Off unless
`phone_enabled` is true. Anyone who can reach the port can load the page,
but nothing works without the secret token: the first WebSocket message
must be {"type": "auth", "token": ...}. Repeated wrong tokens lock the
address out. Requests from here can't run power actions (see
SkillRegistry.handle(allow_confirm=False)).

The connection is plain HTTP, so on a network you don't trust, put it
behind Tailscale (encrypted) and bind phone_host to the Tailscale address.
"""

import asyncio
import hmac
import json
import secrets
import threading
import time
from http import HTTPStatus
from pathlib import Path

from loguru import logger
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

PAGE = Path(__file__).with_name("page.html")

MAX_MESSAGE_BYTES = 4096
MAX_TEXT_CHARS = 500
AUTH_TIMEOUT = 5.0
MAX_FAILURES = 5
FAILURE_WINDOW = 60.0
LOCKOUT_SECONDS = 300.0


def load_or_create_token(path: Path) -> str:
    """The secret lives in data/ (git-ignored). Delete the file to rotate it."""

    try:
        token = path.read_text(encoding="utf-8").strip()

        if len(token) >= 20:
            return token

    except OSError:
        pass

    token = secrets.token_urlsafe(24)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")

    return token


class AuthGuard:
    """Counts wrong tokens per address and locks repeat offenders out."""

    def __init__(self, clock=time.monotonic):

        self._clock = clock
        self._failures = {}           # address -> [timestamps]
        self._locked_until = {}

    def locked(self, address) -> bool:

        until = self._locked_until.get(address)

        if until is None:
            return False

        if self._clock() >= until:
            del self._locked_until[address]
            self._failures.pop(address, None)
            return False

        return True

    def failed(self, address):

        now = self._clock()

        recent = [t for t in self._failures.get(address, []) if now - t < FAILURE_WINDOW]
        recent.append(now)
        self._failures[address] = recent

        if len(recent) >= MAX_FAILURES:
            self._locked_until[address] = now + LOCKOUT_SECONDS
            logger.warning(f"Phone: too many wrong tokens from {address}; locked out.")

    def succeeded(self, address):
        self._failures.pop(address, None)


class PhoneServer:

    def __init__(self, ask, token, host="0.0.0.0", port=8766, guard=None):

        self.ask = ask               # blocking: text -> reply
        self._token = token
        self.host = host
        self.port = port
        self.guard = guard or AuthGuard()

        self.loop = None
        self._thread = None
        self._stop = None
        self._ready = threading.Event()
        self._error = None

    # ---- lifecycle ----------------------------------------------

    def start(self) -> bool:

        self.loop = asyncio.new_event_loop()

        self._thread = threading.Thread(target=self._run, name="TorquePhone", daemon=True)
        self._thread.start()

        self._ready.wait(5)

        if self._error:
            logger.error(f"Phone server could not start: {self._error}")
            return False

        return True

    def stop(self):

        if self.loop and self._stop:
            self.loop.call_soon_threadsafe(self._stop.set)

        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):

        asyncio.set_event_loop(self.loop)

        try:
            self.loop.run_until_complete(self._serve())
        except Exception as error:  # noqa: BLE001
            self._error = error
            self._ready.set()

    async def _serve(self):

        self._stop = asyncio.Event()

        async with serve(
            self._handler,
            self.host,
            self.port,
            process_request=self._process_request,
            max_size=MAX_MESSAGE_BYTES,
        ) as server:

            self.port = server.sockets[0].getsockname()[1]

            self._ready.set()

            await self._stop.wait()

    # ---- HTTP: the page -----------------------------------------

    @staticmethod
    def _process_request(connection, request):

        if request.headers.get("Upgrade", "").lower() == "websocket":
            return None                                   # a WebSocket: handled below

        if request.path.split("?")[0] not in ("/", "/index.html"):
            return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")

        response = connection.respond(HTTPStatus.OK, PAGE.read_text(encoding="utf-8"))

        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
            "connect-src 'self' ws: wss:; base-uri 'none'; form-action 'none'"
        )

        return response

    # ---- WebSocket ----------------------------------------------

    async def _handler(self, websocket):

        address = websocket.remote_address[0] if websocket.remote_address else "?"

        if self.guard.locked(address):
            await websocket.close(4429, "locked out")
            return

        try:
            if not await self._authenticate(websocket, address):
                return

            async for raw in websocket:
                await self._on_message(websocket, raw)

        except ConnectionClosed:
            pass

    async def _authenticate(self, websocket, address) -> bool:

        try:
            raw = await asyncio.wait_for(websocket.recv(), AUTH_TIMEOUT)
            message = json.loads(raw)

            token = message.get("token", "") if message.get("type") == "auth" else ""

        except (asyncio.TimeoutError, ValueError, AttributeError, TypeError):
            token = ""

        if isinstance(token, str) and hmac.compare_digest(token.encode(), self._token.encode()):

            self.guard.succeeded(address)

            await websocket.send(json.dumps({"type": "auth", "ok": True}))

            logger.info("Phone connected.")

            return True

        self.guard.failed(address)

        await websocket.close(4401, "unauthorised")

        return False

    async def _on_message(self, websocket, raw):

        try:
            message = json.loads(raw)
            text = str(message["text"]).strip() if message.get("type") == "text" else ""
            request_id = message.get("id")

        except (ValueError, KeyError, AttributeError, TypeError):
            await websocket.send(json.dumps({"type": "error", "message": "Bad message."}))
            return

        if not text or len(text) > MAX_TEXT_CHARS:
            await websocket.send(json.dumps({"type": "error", "id": request_id, "message": "Empty or too long."}))
            return

        reply = await asyncio.get_running_loop().run_in_executor(None, self.ask, text)

        await websocket.send(json.dumps({"type": "reply", "id": request_id, "text": reply}))
