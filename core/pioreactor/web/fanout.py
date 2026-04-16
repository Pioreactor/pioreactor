# -*- coding: utf-8 -*-
import typing as t

from pioreactor.web import tasks
from pioreactor.web.app import get_all_units
from pioreactor.web.app import get_all_workers
from pioreactor.web.app import get_all_workers_in_experiment


def broadcast_get_across_cluster(endpoint: str, timeout: float = 5.0, return_raw: bool = False) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint, units=get_all_units(), timeout=timeout, return_raw=return_raw
    )


def broadcast_post_across_cluster(
    endpoint: str,
    json: dict[str, t.Any] | None = None,
    params: dict[str, t.Any] | None = None,
    timeout: float = 30.0,
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_post(endpoint, get_all_units(), json=json, params=params, timeout=timeout)


def broadcast_delete_across_cluster(
    endpoint: str, json: dict[str, t.Any] | None = None, timeout: float = 30.0
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_delete(endpoint, get_all_units(), json=json, timeout=timeout)


def broadcast_patch_across_cluster(
    endpoint: str, json: dict[str, t.Any] | None = None, timeout: float = 30.0
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_patch(endpoint, get_all_units(), json=json, timeout=timeout)


def broadcast_get_across_workers(endpoint: str, timeout: float = 5.0, return_raw: bool = False) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint, units=get_all_workers(), timeout=timeout, return_raw=return_raw
    )


def broadcast_get_across_workers_in_experiment(
    endpoint: str, experiment: str, timeout: float = 5.0, return_raw: bool = False
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_get(
        endpoint=endpoint,
        units=get_all_workers_in_experiment(experiment),
        timeout=timeout,
        return_raw=return_raw,
    )


def broadcast_post_across_workers(
    endpoint: str,
    json: dict[str, t.Any] | None = None,
    params: dict[str, t.Any] | None = None,
    timeout: float = 30.0,
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_post(endpoint, get_all_workers(), json=json, params=params, timeout=timeout)


def broadcast_delete_across_workers(
    endpoint: str, json: dict[str, t.Any] | None = None, timeout: float = 30.0
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_delete(endpoint, get_all_workers(), json=json, timeout=timeout)


def broadcast_patch_across_workers(
    endpoint: str, json: dict[str, t.Any] | None = None, timeout: float = 30.0
) -> t.Any:
    assert endpoint.startswith("/unit_api")
    return tasks.multicast_patch(endpoint, get_all_workers(), json=json, timeout=timeout)
