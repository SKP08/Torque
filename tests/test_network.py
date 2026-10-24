import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from torque.network import geoip as geoip_module
from torque.network.geoip import CENTROIDS, GeoIP
from torque.network.live import network_snapshot, spoken_network
from torque.skills.hud_skills import build_hud_skills
from torque.skills.registry import SkillRegistry

REAL_DB = Path(os.environ.get("TORQUE_GEOIP", "/tmp/claude-0/geo/d/package/dbip-country.mmdb"))


class FakeGeo:
    available = True
    TABLE = {"8.8.8.8": "US", "1.1.1.1": "AU", "52.1.1.1": "US", "49.36.0.1": "IN"}

    def place(self, ip):
        code = self.TABLE.get(ip)
        if not code:
            return None
        lat, lon, name = CENTROIDS[code]
        return {"code": code, "country": name, "lat": lat, "lon": lon}


def conns(*pairs):
    return lambda: list(pairs)


def test_centroids_cover_the_world():
    assert len(CENTROIDS) >= 240
    lat, lon, name = CENTROIDS["IN"]
    assert name == "India" and 5 < lat < 35 and 65 < lon < 95


def test_snapshot_groups_by_country_and_ranks():
    data = network_snapshot(FakeGeo(), conns(("chrome.exe", "8.8.8.8"), ("chrome.exe", "52.1.1.1"),
                                             ("discord.exe", "1.1.1.1"), ("chrome.exe", "9.9.9.9")),
                            home={"lat": 43.9, "lon": -78.9})
    assert data["kind"] == "network" and data["home"] == {"lat": 43.9, "lon": -78.9}
    assert [c["country"] for c in data["connections"]] == ["United States", "Australia"]
    assert data["connections"][0]["count"] == 2 and data["connections"][0]["process"] == "chrome.exe"
    assert data["total"] == 4 and data["unknown"] == 1
    assert json.dumps(data)                       # serialisable for the websocket


def test_snapshot_empty_and_unplaceable():
    assert network_snapshot(FakeGeo(), conns())["connections"] == []
    assert "don't see any" in spoken_network(network_snapshot(FakeGeo(), conns()))
    unplaced = network_snapshot(FakeGeo(), conns(("a.exe", "9.9.9.9")))
    assert "can't place" in spoken_network(unplaced)


def test_spoken_summary():
    data = network_snapshot(FakeGeo(), conns(("a", "8.8.8.8"), ("a", "1.1.1.1"), ("a", "49.36.0.1")))
    text = spoken_network(data)
    assert "3 outside connections across 3 countries" in text and "United States" in text or "Australia" in text


def test_private_addresses_are_never_reported():
    from torque.network.live import _public
    for ip in ("192.168.1.5", "10.0.0.2", "127.0.0.1", "169.254.1.1", "::1", "nonsense"):
        assert not _public(ip)
    assert _public("8.8.8.8")


def test_missing_database_is_handled(tmp_path):
    g = GeoIP(tmp_path / "nope.mmdb")
    assert not g.available and g.country_code("8.8.8.8") is None and g.place("8.8.8.8") is None


@pytest.mark.skipif(not REAL_DB.exists(), reason="DB-IP country database not downloaded")
def test_real_database_lookups():
    g = GeoIP(REAL_DB)
    assert g.available
    assert g.country_code("8.8.8.8") == "US"
    assert g.country_code("1.1.1.1") == "AU"
    assert g.country_code("2a00:1450:4001::1") == "DE"
    assert g.country_code("192.168.1.1") is None
    assert g.country_code("garbage") is None
    place = g.place("49.36.0.1")
    assert place["code"] == "IN" and place["country"] == "India"


@pytest.mark.skipif(not REAL_DB.exists(), reason="DB-IP country database not downloaded")
def test_real_database_end_to_end_snapshot():
    data = network_snapshot(GeoIP(REAL_DB), conns(("chrome.exe", "8.8.8.8"), ("python.exe", "49.36.0.1")))
    assert {c["country"] for c in data["connections"]} == {"United States", "India"}


def fake_package(size):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"x" * size
        info = tarfile.TarInfo(geoip_module.MEMBER)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def opener_for(tarball):
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def opener(url, timeout=None):
        if url == geoip_module.PACKAGE:
            return Response(json.dumps({"dist": {"tarball": "https://example.test/db.tgz"}}).encode())
        assert url == "https://example.test/db.tgz"
        return Response(tarball)

    return opener


def test_download_extracts_atomically(tmp_path, monkeypatch):
    monkeypatch.setattr(geoip_module, "MIN_BYTES", 100)
    dest = geoip_module.download(tmp_path / "geo" / "db.mmdb", opener_for(fake_package(500)))
    assert dest.read_bytes() == b"x" * 500 and not list(dest.parent.glob("*.part"))


def test_truncated_download_is_rejected(tmp_path):
    with pytest.raises(RuntimeError):
        geoip_module.download(tmp_path / "db.mmdb", opener_for(fake_package(500)))
    assert not (tmp_path / "db.mmdb").exists()


def test_network_skill_by_voice():
    shown = []
    data = {"kind": "network", "home": None, "total": 2, "unknown": 0,
            "connections": [{"lat": 1, "lon": 2, "country": "India", "process": "x", "count": 2}]}
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {}, network_fn=lambda: data))

    for phrase in ("show my network", "show me the network globe", "where is my pc connecting",
                   "who am I connected to", "network map", "hey torque show my connections"):
        shown.clear()
        said = registry.handle(phrase, hud=shown.append)
        assert said and "India" in said and shown == [data], phrase


def test_network_skill_without_database_or_when_off():
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {}, network_fn=lambda: None))
    assert "database" in registry.handle("show my network")
    off = SkillRegistry(build_hud_skills(status_fn=lambda: {}))
    assert "switched off" in off.handle("show my network")


def test_network_phrases_do_not_swallow_other_requests():
    registry = SkillRegistry(build_hud_skills(status_fn=lambda: {}, network_fn=lambda: None))
    for phrase in ("how do i connect to wifi", "show my files", "open network settings"):
        assert registry.handle(phrase) is None, phrase
