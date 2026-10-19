# -*- coding: utf-8 -*-
import typing as t

from pioreactor.web import tasks
from pioreactor.web.app import get_all_existing_workers_ever_assigned_to_experiment
from pioreactor.web.app import get_all_units
from pioreactor.web.app import get_all_workers
from pioreactor.web.app import get_all_workers_in_experiment
from pioreactor.web.tasks import UnitApiMethod

# Each helper sends one request to every unit in a group. Keyword arguments pass through to tasks.multicast.


def broadcast_across_cluster(
    method: UnitApiMethod, endpoint: str, json: dict[str, t.Any] | None = None, **kwargs: t.Any
) -> t.Any:
    return tasks.multicast(method, endpoint, get_all_units(), json=json, **kwargs)


def broadcast_across_workers(
    method: UnitApiMethod, endpoint: str, json: dict[str, t.Any] | None = None, **kwargs: t.Any
) -> t.Any:
    return tasks.multicast(method, endpoint, get_all_workers(), json=json, **kwargs)


def broadcast_across_workers_in_experiment(
    method: UnitApiMethod, endpoint: str, experiment: str, **kwargs: t.Any
) -> t.Any:
    return tasks.multicast(method, endpoint, get_all_workers_in_experiment(experiment), **kwargs)


def broadcast_across_existing_workers_ever_assigned_to_experiment(
    method: UnitApiMethod, endpoint: str, experiment: str, **kwargs: t.Any
) -> t.Any:
    return tasks.multicast(
        method, endpoint, get_all_existing_workers_ever_assigned_to_experiment(experiment), **kwargs
    )
