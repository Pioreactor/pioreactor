# -*- coding: utf-8 -*-
from time import time
from typing import Any

from huey.api import Result
from msgspec import DecodeError
from msgspec import Struct
from msgspec.json import decode as json_decode
from msgspec.json import encode as json_encode
from pioreactor import types as pt
from pioreactor.utils import local_intermittent_storage
from pioreactor.web import tasks
from pioreactor.web.app import get_all_units
from pioreactor.web.app import get_all_workers
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


class CachedGetEntry(Struct):
    value: Any
    cached_at: float


class MulticastGetCacheTarget(Struct, frozen=True):
    namespace: str
    endpoint: str


CALIBRATIONS = MulticastGetCacheTarget("calibrations", "/unit_api/calibrations")
ACTIVE_CALIBRATIONS = MulticastGetCacheTarget("active_calibrations", "/unit_api/active_calibrations")
CALIBRATION_PROTOCOLS = MulticastGetCacheTarget("calibration_protocols", "/unit_api/calibration_protocols")
ACTIVE_ESTIMATORS = MulticastGetCacheTarget("active_estimators", "/unit_api/active_estimators")
ESTIMATORS = MulticastGetCacheTarget("estimators", "/unit_api/estimators")
PLUGINS_INSTALLED = MulticastGetCacheTarget("plugins_installed", "/unit_api/plugins/installed")

LEADER_MULTICAST_GET_CACHE = "leader_multicast_get_cache"


def _multicast_get_cache_key(cache_namespace: str, endpoint: str, unit: pt.Unit) -> tuple[str, str, str, str]:
    return ("multicast_get", cache_namespace, endpoint, unit)


def _read_multicast_get_cache_entry(
    cache_store: Any,
    *,
    cache_namespace: str,
    endpoint: str,
    unit: str,
    ttl_s: float,
) -> tuple[bool, Any]:
    key = _multicast_get_cache_key(cache_namespace, endpoint, unit)
    raw_entry = cache_store.get(key)
    if raw_entry is None:
        return False, None

    try:
        entry = json_decode(raw_entry, type=CachedGetEntry)
    except DecodeError:
        cache_store.pop(key, None)
        return False, None

    if (time() - entry.cached_at) > ttl_s:
        cache_store.pop(key, None)
        return False, None

    return True, entry.value


def clear_multicast_get_cache(cache_namespace: str, endpoint: str, units: list[str]) -> None:
    with local_intermittent_storage(LEADER_MULTICAST_GET_CACHE) as cache_store:
        for unit in units:
            cache_store.pop(_multicast_get_cache_key(cache_namespace, endpoint, unit), None)


def multicast_get_with_leader_cache(
    cache_namespace: str,
    endpoint: str,
    units: list[str],
    timeout: float = 5.0,
    ttl_s: float = 10.0,
) -> dict[str, Any]:
    assert endpoint.startswith("/unit_api")

    sorted_units = sorted(units)
    cached_results: dict[str, Any] = {}
    cache_misses: list[str] = []

    with local_intermittent_storage(LEADER_MULTICAST_GET_CACHE) as cache_store:
        for unit in sorted_units:
            is_hit, value = _read_multicast_get_cache_entry(
                cache_store,
                cache_namespace=cache_namespace,
                endpoint=endpoint,
                unit=unit,
                ttl_s=ttl_s,
            )
            if is_hit:
                cached_results[unit] = value
            else:
                cache_misses.append(unit)

    if not cache_misses:
        return cached_results

    fetched_results = tasks._multicast_get_uncached(endpoint=endpoint, units=cache_misses, timeout=timeout)

    with local_intermittent_storage(LEADER_MULTICAST_GET_CACHE) as cache_store:
        for unit, value in fetched_results.items():
            if value is None:
                continue

            blob = json_encode(CachedGetEntry(cached_at=time(), value=value))
            key = _multicast_get_cache_key(cache_namespace, endpoint, unit)
            cache_store[key] = blob

    cached_results.update(fetched_results)
    return dict(sorted(cached_results.items()))


def cached_multicast_get(
    target: MulticastGetCacheTarget,
    units: list[str],
    *,
    timeout: float = 5.0,
) -> Result:
    return tasks.multicast_get_with_leader_cache(
        target.namespace,
        target.endpoint,
        units,
        timeout=timeout,
    )


def invalidate_multicast_get_cache(targets: list[MulticastGetCacheTarget], units: list[str]) -> None:
    for target in targets:
        clear_multicast_get_cache(target.namespace, target.endpoint, units)


def invalidate_calibrations_cache(pioreactor_unit: str) -> None:
    units = get_all_workers() if pioreactor_unit == UNIVERSAL_IDENTIFIER else [pioreactor_unit]
    invalidate_multicast_get_cache([CALIBRATIONS, ACTIVE_CALIBRATIONS], units)


def invalidate_calibration_protocols_cache(pioreactor_unit: str) -> None:
    units = get_all_workers() if pioreactor_unit == UNIVERSAL_IDENTIFIER else [pioreactor_unit]
    invalidate_multicast_get_cache([CALIBRATION_PROTOCOLS], units)


def invalidate_estimators_cache(pioreactor_unit: str) -> None:
    units = get_all_workers() if pioreactor_unit == UNIVERSAL_IDENTIFIER else [pioreactor_unit]
    invalidate_multicast_get_cache([ACTIVE_ESTIMATORS, ESTIMATORS], units)


def invalidate_plugins_installed_cache(pioreactor_unit: str) -> None:
    units = get_all_units() if pioreactor_unit == UNIVERSAL_IDENTIFIER else [pioreactor_unit]
    invalidate_multicast_get_cache([PLUGINS_INSTALLED], units)
