import os
import time
import urllib.request

from torque.ui.static_server import StaticServer
from torque.ui.ui_launcher import build_is_stale, find_electron


def fetch(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.headers, r.read()


def test_static_server_serves_files_with_correct_mime_types(tmp_path):
    (tmp_path / "index.html").write_text("<h1>hi</h1>")
    (tmp_path / "app.js").write_text("export default 1")
    (tmp_path / "app.css").write_text("a{}")

    server = StaticServer(tmp_path, port=0)
    assert server.start()
    try:
        status, headers, body = fetch(server.url + "/")
        assert status == 200 and b"hi" in body

        _, headers, _ = fetch(server.url + "/app.js")
        assert headers["Content-Type"].startswith("text/javascript")     # not text/plain

        _, headers, _ = fetch(server.url + "/app.css")
        assert headers["Content-Type"].startswith("text/css")
        assert headers["Cache-Control"] == "no-store"
    finally:
        server.stop()


def test_static_server_binds_to_loopback_only(tmp_path):
    server = StaticServer(tmp_path, port=0)
    server.start()
    try:
        assert server.host == "127.0.0.1"
        assert server._server.server_address[0] == "127.0.0.1"
    finally:
        server.stop()


def test_static_server_reports_port_in_use(tmp_path):
    first = StaticServer(tmp_path, port=0)
    first.start()
    try:
        second = StaticServer(tmp_path, port=first.port)
        assert second.start() is False
    finally:
        first.stop()


def test_static_server_cannot_escape_its_directory(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "secret.txt").write_text("nope")
    server = StaticServer(tmp_path / "public", port=0)
    server.start()
    try:
        import urllib.error
        try:
            status, _, body = fetch(server.url + "/..%2fsecret.txt")
        except urllib.error.HTTPError as error:
            status, body = error.code, b""
        assert status == 404 and b"nope" not in body
    finally:
        server.stop()


def test_build_is_stale_logic(tmp_path):
    assert build_is_stale(tmp_path)                       # no dist at all

    (tmp_path / "src").mkdir()
    (tmp_path / "dist").mkdir()
    source = tmp_path / "src" / "App.jsx"
    source.write_text("x")
    index = tmp_path / "dist" / "index.html"
    index.write_text("x")

    now = time.time()
    os.utime(source, (now - 100, now - 100))
    os.utime(index, (now, now))
    assert not build_is_stale(tmp_path)                   # build is newer

    os.utime(source, (now + 50, now + 50))
    assert build_is_stale(tmp_path)                       # source edited since


def test_find_electron(tmp_path):
    assert find_electron(tmp_path) is None

    package = tmp_path / "node_modules" / "electron"
    (package / "dist").mkdir(parents=True)
    (package / "path.txt").write_text("electron.exe")
    assert find_electron(tmp_path) is None                # path.txt but no binary

    (package / "dist" / "electron.exe").write_text("")
    assert find_electron(tmp_path) == package / "dist" / "electron.exe"
