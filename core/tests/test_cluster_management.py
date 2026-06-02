# -*- coding: utf-8 -*-
"""
Tests for cluster_management API interactions against the leader webserver.
"""
import pytest
from click.testing import CliRunner
from pioreactor import cluster_management
from pioreactor.cluster_management import add_worker
from pioreactor.cluster_management import cluster_status
from pioreactor.cluster_management import get_active_workers_in_experiment
from pioreactor.cluster_management import get_active_workers_in_inventory
from pioreactor.cluster_management import get_workers_in_experiment
from pioreactor.cluster_management import get_workers_in_inventory
from pioreactor.mureq import Response
from pioreactor.utils.networking import DiscoveredWorker


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


def test_add_worker_falls_back_from_stale_config_address_to_discovered_ipv4(monkeypatch) -> None:
    captured_run_args: list[str] = []

    class FakeCompletedProcess:
        returncode = 0
        stderr = ""

    class FakeLeaderResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeLogger:
        def info(self, *_args: object, **_kwargs: object) -> None:
            return None

        def error(self, *_args: object, **_kwargs: object) -> None:
            return None

        def notice(self, *_args: object, **_kwargs: object) -> None:
            return None

    monkeypatch.setattr(cluster_management.config, "get", lambda *_args, **_kwargs: "192.168.1.50")
    monkeypatch.setattr(
        cluster_management.networking,
        "discover_workers_on_network",
        lambda terminate: iter([DiscoveredWorker(hostname="unit1", ipv4_address="192.168.1.99")]),
    )
    monkeypatch.setattr(
        cluster_management.networking,
        "is_address_on_network",
        lambda address, timeout=10.0: address == "192.168.1.99",
    )
    monkeypatch.setattr(cluster_management.whoami, "get_unit_name", lambda: "leader")
    monkeypatch.setattr(cluster_management.whoami, "is_testing_env", lambda: False)
    monkeypatch.setattr(cluster_management, "create_logger", lambda *_args, **_kwargs: FakeLogger())
    monkeypatch.setattr(cluster_management, "put_into_leader", lambda *_args, **_kwargs: FakeLeaderResponse())

    def fake_run(args: list[str], **_kwargs: object) -> FakeCompletedProcess:
        captured_run_args.extend(args)
        return FakeCompletedProcess()

    monkeypatch.setattr(cluster_management.subprocess, "run", fake_run)

    result = CliRunner().invoke(add_worker, ["unit1"])

    assert result.exit_code == 0
    assert captured_run_args == [
        "bash",
        "/usr/local/bin/add_new_pioreactor_worker_from_leader.sh",
        "unit1",
        "raspberry",
        "192.168.1.99",
    ]


def test_add_worker_explicit_address_does_not_try_config_or_discovery(monkeypatch) -> None:
    captured_addresses: list[str] = []
    discovery_was_called = False

    class FakeCompletedProcess:
        returncode = 0
        stderr = ""

    class FakeLeaderResponse:
        def raise_for_status(self) -> None:
            return None

    class FakeLogger:
        def info(self, *_args: object, **_kwargs: object) -> None:
            return None

        def error(self, *_args: object, **_kwargs: object) -> None:
            return None

        def notice(self, *_args: object, **_kwargs: object) -> None:
            return None

    def discover_workers_on_network(terminate: bool):
        nonlocal discovery_was_called
        discovery_was_called = True
        return iter([DiscoveredWorker(hostname="unit1", ipv4_address="192.168.1.99")])

    monkeypatch.setattr(cluster_management.config, "get", lambda *_args, **_kwargs: "192.168.1.50")
    monkeypatch.setattr(
        cluster_management.networking,
        "discover_workers_on_network",
        discover_workers_on_network,
    )
    monkeypatch.setattr(cluster_management.whoami, "get_unit_name", lambda: "leader")
    monkeypatch.setattr(cluster_management.whoami, "is_testing_env", lambda: False)
    monkeypatch.setattr(cluster_management, "create_logger", lambda *_args, **_kwargs: FakeLogger())
    monkeypatch.setattr(cluster_management, "put_into_leader", lambda *_args, **_kwargs: FakeLeaderResponse())

    def fake_is_address_on_network(address: str, timeout: float = 10.0) -> bool:
        captured_addresses.append(address)
        return True

    def fake_run(_args: list[str], **_kwargs: object) -> FakeCompletedProcess:
        return FakeCompletedProcess()

    monkeypatch.setattr(cluster_management.networking, "is_address_on_network", fake_is_address_on_network)
    monkeypatch.setattr(cluster_management.subprocess, "run", fake_run)

    result = CliRunner().invoke(add_worker, ["unit1", "--address", "unit1.local"])

    assert result.exit_code == 0
    assert captured_addresses == ["unit1.local"]
    assert discovery_was_called is False
