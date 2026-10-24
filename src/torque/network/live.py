import ipaddress
from collections import Counter

import psutil

MAX_DESTINATIONS = 24


def _public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def established_connections():
    """[(process_name, remote_ip)] for connections to public addresses."""

    out = []

    try:
        connections = psutil.net_connections(kind="inet")
    except (psutil.Error, OSError):
        return out

    names = {}

    for c in connections:
        if c.status != psutil.CONN_ESTABLISHED or not c.raddr or not _public(c.raddr.ip):
            continue

        if c.pid not in names:
            try:
                names[c.pid] = psutil.Process(c.pid).name()
            except (psutil.Error, TypeError):
                names[c.pid] = "unknown"

        out.append((names[c.pid], c.raddr.ip))

    return out


def network_snapshot(geoip, connections_fn=established_connections, home=None) -> dict:
    """
    HUD payload: where this PC is talking to right now, grouped by country.

    home is {"lat","lon"} or None (then the globe shows destinations without arcs).
    """

    groups = {}
    unknown = 0

    for process, ip in connections_fn():
        place = geoip.place(ip)

        if not place:
            unknown += 1
            continue

        group = groups.setdefault(place["code"], {**place, "count": 0, "processes": Counter()})
        group["count"] += 1
        group["processes"][process] += 1

    ranked = sorted(groups.values(), key=lambda g: -g["count"])[:MAX_DESTINATIONS]

    return {
        "kind": "network",
        "home": home,
        "connections": [{"lat": g["lat"], "lon": g["lon"], "country": g["country"],
                         "process": g["processes"].most_common(1)[0][0], "count": g["count"]}
                        for g in ranked],
        "total": sum(g["count"] for g in groups.values()) + unknown,
        "unknown": unknown,
    }


def spoken_network(snapshot: dict) -> str:
    connections = snapshot["connections"]

    if not connections:
        return "I don't see any outside connections right now." if not snapshot["total"] \
            else f"I see {snapshot['total']} outside connections, but I can't place them."

    top = ", ".join(f"{c['country']}" for c in connections[:3])
    countries = len(connections)

    return (f"You have {snapshot['total']} outside connections across {countries} "
            f"{'country' if countries == 1 else 'countries'}, mostly {top}.")
