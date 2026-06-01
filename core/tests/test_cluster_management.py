# -*- coding: utf-8 -*-
"""
Tests for cluster_management API interactions against the leader webserver.
"""
import pytest
from click.testing import CliRunner
from pioreactor.cluster_management import cluster_status
from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.cluster_management import get_active_workers_in_inventory
from pioreactor.cluster_management import get_workers_in_experiment
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.mureq import Response


def test_get_workers_in_inventory(active_workers_in_cluster) -> None:
    """get_workers_in_inventory should return all workers including inactive ones"""
    units = get_workers_in_inventory()
    assert isinstance(units, tuple)
    # mock returns active_workers plus one notactiveworker
    expected = set(active_workers_in_cluster) | {"notactiveworker"}
    assert set(units) == expected


def test_get_active_workers_in_inventory(active_workers_in_cluster) -> None:
    """get_active_workers_in_inventory should return only active workers"""
    units = get_active_workers_in_inventory()
    assert isinstance(units, tuple)
    assert set(units) == set(active_workers_in_cluster)


@pytest.mark.parametrize("experiment", ["testexp", "another"])
def test_get_workers_in_experiment(active_workers_in_cluster, experiment) -> None:
    """get_workers_in_experiment should return workers for a given experiment"""
    units = get_workers_in_experiment(experiment)
    assert isinstance(units, tuple)
    # mock returns only active workers for experiment
    assert set(units) == set(active_workers_in_cluster)


@pytest.mark.parametrize("experiment", ["testexp", "another"])
def test_get_active_workers_in_experiment(active_workers_in_cluster, experiment) -> None:
    """get_active_workers_in_experiment should return only active workers for a given experiment"""
    units = get_active_workers_in_experiment(experiment)
    assert isinstance(units, tuple)
    assert set(units) == set(active_workers_in_cluster)


def test_cluster_status_surfaces_structured_api_error(monkeypatch) -> None:
    monkeypatch.setattr(
        "pioreactor.cluster_management.get_from_leader",
        lambda *_args, **_kwargs: Response(
            "http://localhost:4999/api/workers",
            503,
            {"Content-Type": "application/json"},
            (
                b'{"error":"Unable to list workers.","status":503,'
                b'"cause":"Database is unavailable.","remediation":"Retry after the database starts."}'
            ),
        ),
    )

    result = CliRunner().invoke(cluster_status)

    assert result.exit_code == 1
    assert result.output == (
        "Error: Unable to get workers. HTTP 503: Unable to list workers. "
        "Cause: Database is unavailable. Remediation: Retry after the database starts.\n"
    )
