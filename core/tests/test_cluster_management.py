# -*- coding: utf-8 -*-
"""
Tests for cluster_management API interactions against the leader webserver.
"""
from __future__ import annotations

import pytest
from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.cluster_management import get_active_workers_in_inventory
from pioreactor.cluster_management import get_workers_in_experiment
from pioreactor.cluster_management import get_workers_in_inventory


def test_get_workers_in_inventory(active_workers_in_cluster):
    """get_workers_in_inventory should return all workers including inactive ones"""
    units = get_workers_in_inventory()
    assert isinstance(units, tuple)
    # mock returns active_workers plus one notactiveworker
    expected = set(active_workers_in_cluster) | {"notactiveworker"}
    assert set(units) == expected


def test_get_active_workers_in_inventory(active_workers_in_cluster):
    """get_active_workers_in_inventory should return only active workers"""
    units = get_active_workers_in_inventory()
    assert isinstance(units, tuple)
    assert set(units) == set(active_workers_in_cluster)


@pytest.mark.parametrize("experiment", ["testexp", "another"])
def test_get_workers_in_experiment(active_workers_in_cluster, experiment):
    """get_workers_in_experiment should return workers for a given experiment"""
    units = get_workers_in_experiment(experiment)
    assert isinstance(units, tuple)
    # mock returns only active workers for experiment
    assert set(units) == set(active_workers_in_cluster)


@pytest.mark.parametrize("experiment", ["testexp", "another"])
def test_get_active_workers_in_experiment(active_workers_in_cluster, experiment):
    """get_active_workers_in_experiment should return only active workers for a given experiment"""
    units = get_active_workers_in_experiment(experiment)
    assert isinstance(units, tuple)
    assert set(units) == set(active_workers_in_cluster)
