# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.config import leader_address
from pioreactor.mureq import get


def get_workers_in_inventory() -> tuple[str, ...]:
    result = get(f"http://{leader_address}/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_inventory() -> tuple[str, ...]:
    result = get(f"http://{leader_address}/api/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))


def get_workers_in_experiment(experiment: str) -> tuple[str, ...]:
    result = get(f"http://{leader_address}/api/experiments/{experiment}/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json())


def get_active_workers_in_experiment(experiment: str) -> tuple[str, ...]:
    result = get(f"http://{leader_address}/api/experiments/{experiment}/workers")
    return tuple(worker["pioreactor_unit"] for worker in result.json() if bool(worker["is_active"]))
