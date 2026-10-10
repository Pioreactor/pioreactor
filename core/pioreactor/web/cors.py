# -*- coding: utf-8 -*-
"""
Cross-origin access to the leader's /api.

Each Pioreactor's touchscreen loads its UI from its own web server, so every call it
makes to the leader is cross-origin. Origins are allowlisted from the cluster
inventory (never `*`), so a random website open on a lab computer can't read
cluster data or send JSON commands.
"""
import typing as t
from time import monotonic
from urllib.parse import urlsplit

from flask import request
from pioreactor.config import ConfigParserMod
from pioreactor.paths import get_dot_pioreactor_path

# Where each kiosk loads its UI from. Any port is allowed (useful in development).
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})
ALLOWED_SCHEMES = frozenset({"http", "https"})

ALLOW_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
ALLOW_HEADERS = "Content-Type, Accept, X-Pioreactor-Target"
# Preflight caching matters on a slow screen: without it, every JSON write costs an
# extra round trip. WebKit caps this at 600 s.
MAX_AGE_S = "600"

ALLOWED_HOSTS_TTL_S = 30.0

_allowed_hosts_cache: tuple[float, frozenset[str]] | None = None


def clear_allowed_hosts_cache() -> None:
    global _allowed_hosts_cache
    _allowed_hosts_cache = None


def _compute_cluster_hosts() -> frozenset[str]:
    from pioreactor.web.app import get_all_units

    config = ConfigParserMod()
    config.read(get_dot_pioreactor_path() / "config.ini")

    hosts: set[str] = set()
    for unit in get_all_units():
        unit = unit.strip().lower()
        if not unit:
            continue
        hosts.add(unit)
        hosts.add(unit.removesuffix(".local") + ".local")
        address = config.get("cluster.addresses", unit, fallback="").strip().lower()
        if address:
            hosts.add(address)
    return frozenset(hosts)


def get_cluster_hosts() -> frozenset[str]:
    # Cached briefly so each request doesn't hit the database or re-read config.
    global _allowed_hosts_cache
    now = monotonic()
    if _allowed_hosts_cache is not None and now - _allowed_hosts_cache[0] < ALLOWED_HOSTS_TTL_S:
        return _allowed_hosts_cache[1]
    hosts = _compute_cluster_hosts()
    _allowed_hosts_cache = (now, hosts)
    return hosts


def is_allowed_origin(origin: str) -> bool:
    try:
        parts = urlsplit(origin)
        port = parts.port
    except ValueError:
        return False

    host = parts.hostname
    if parts.scheme not in ALLOWED_SCHEMES or not host or parts.path or parts.query:
        return False

    if host in LOCAL_HOSTS:
        return True

    # Cluster members serve their screens on the default port.
    if port is not None:
        return False

    try:
        return host in get_cluster_hosts()
    except Exception:
        return False


def add_cors_headers(response: t.Any) -> t.Any:
    if not request.path.startswith("/api/"):
        return response

    response.vary.add("Origin")

    origin = request.headers.get("Origin")
    if not origin or not is_allowed_origin(origin):
        return response

    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = ALLOW_METHODS
    response.headers["Access-Control-Allow-Headers"] = ALLOW_HEADERS
    response.headers["Access-Control-Max-Age"] = MAX_AGE_S
    return response
