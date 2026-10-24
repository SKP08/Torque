"""
Offline IP -> country lookup (DB-IP "IP to Country Lite", CC BY 4.0, https://db-ip.com).

Download once:   uv run python -m torque.network.geoip
The lookup never touches the network; nothing about your connections leaves this PC.
"""

import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

from torque.paths import DATA_DIR

DB_PATH = DATA_DIR / "geoip" / "dbip-country.mmdb"
PACKAGE = "https://registry.npmjs.org/@ip-location-db/dbip-country-mmdb/latest"
MEMBER = "package/dbip-country.mmdb"
MIN_BYTES = 4_000_000

CENTROIDS = json.loads((Path(__file__).parent / "centroids.json").read_text(encoding="utf-8"))


class GeoIP:
    """country_code(ip) -> 'US' or None (private, unknown or no database)."""

    def __init__(self, path=DB_PATH):
        self._reader = None

        try:
            import maxminddb

            if Path(path).exists():
                self._reader = maxminddb.open_database(str(path))

        except (ImportError, OSError, ValueError):
            self._reader = None

    @property
    def available(self) -> bool:
        return self._reader is not None

    def country_code(self, ip: str):
        if not self._reader:
            return None

        try:
            record = self._reader.get(ip)
        except (ValueError, OSError):
            return None

        code = (record or {}).get("country_code") if isinstance(record, dict) else None

        return code if code in CENTROIDS else None

    def place(self, ip: str):
        """{'code','country','lat','lon'} for an IP, or None."""

        code = self.country_code(ip)

        if not code:
            return None

        lat, lon, name = CENTROIDS[code]

        return {"code": code, "country": name, "lat": lat, "lon": lon}


def download(dest: Path = DB_PATH, opener=urllib.request.urlopen) -> Path:
    """Fetch the database from the npm registry (a plain tarball), atomically."""

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    with opener(PACKAGE, timeout=30) as response:
        tarball = json.load(response)["dist"]["tarball"]

    with opener(tarball, timeout=120) as response:
        data = response.read()

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        member = archive.extractfile(MEMBER)

        if member is None:
            raise RuntimeError("database not found in package")

        payload = member.read()

    if len(payload) < MIN_BYTES:
        raise RuntimeError(f"database looks truncated ({len(payload)} bytes)")

    part = dest.with_suffix(".part")
    part.write_bytes(payload)
    part.replace(dest)

    return dest


if __name__ == "__main__":
    try:
        print(f"Saved {download()}")
        print("IP-to-country data by DB-IP.com (CC BY 4.0).")
    except Exception as error:  # noqa: BLE001
        print(f"Download failed: {error}", file=sys.stderr)
        sys.exit(1)
