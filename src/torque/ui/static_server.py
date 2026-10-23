import functools
import http.server
import threading

from loguru import logger

# Set explicitly: on Windows the registry can map .js to text/plain, and
# browsers refuse to run module scripts served that way.
MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".wasm": "application/wasm",
    ".woff2": "font/woff2",
    ".map": "application/json",
}


class _Handler(http.server.SimpleHTTPRequestHandler):

    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, **MIME_TYPES}

    def end_headers(self):
        # Always serve the freshest build; it's a local file anyway.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):      # noqa: A002
        logger.trace("ui-server " + format % args)


class StaticServer:
    """Serves the built UI (torque-ui/dist) on 127.0.0.1 only."""

    def __init__(self, directory, port, host="127.0.0.1"):

        self.directory = str(directory)
        self.host = host
        self.port = port
        self._server = None
        self._thread = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> bool:

        handler = functools.partial(_Handler, directory=self.directory)

        try:
            self._server = http.server.ThreadingHTTPServer((self.host, self.port), handler)

        except OSError as error:
            logger.error(f"UI server could not bind {self.host}:{self.port}: {error}")
            return False

        # Port 0 picks a free one (used by tests).
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="TorqueUIServer",
            daemon=True,
        )

        self._thread.start()

        logger.info(f"UI served at {self.url}")

        return True

    def stop(self):

        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
