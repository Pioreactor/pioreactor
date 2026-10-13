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


class _AddWorkerEvents:
    """Stubs everything `pio workers add` touches outside the process, and records the calls."""

    def __init__(self, monkeypatch, join_error: str | None = None) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock
        from pioreactor.exc import SSHError

        self.events: list[tuple] = []

        def run(args: list[str], **kwargs: object) -> SimpleNamespace:
            assert args[0] == "bash"
            self.events.append(("ssh_setup", tuple(args[2:]), kwargs["env"]["SSHPASS"]))
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        def ssh(address: str, command: str, detach: bool = True) -> None:
            if command == "sudo reboot":
                self.events.append(("reboot", address, detach))
                return
            self.events.append(("join", command, detach))
            if join_error is not None:
                raise SSHError(f"SSH command failed: {join_error}")

        def register(endpoint: str, json: dict) -> Response:
            self.events.append(("register", json))
            return Response("http://leader/api/workers", 201, {}, b"{}")

        monkeypatch.setattr(cluster_management.whoami, "get_unit_name", lambda: "leader")
        monkeypatch.setattr(cluster_management.whoami, "is_testing_env", lambda: False)
        monkeypatch.setattr(cluster_management, "create_logger", lambda *_args, **_kwargs: Mock())
        monkeypatch.setattr(cluster_management, "put_into_leader", register)
        monkeypatch.setattr(
            cluster_management,
            "set_config_value_in_file",
            lambda _path, section, key, value: self.events.append(("address", section, key, value)),
        )
        monkeypatch.setattr(
            cluster_management.networking,
            "cp_file_across_cluster",
            lambda unit, _localpath, remotepath, timeout: self.events.append(("copy", unit, remotepath)),
        )
        monkeypatch.setattr(cluster_management.networking, "ssh", ssh)
        monkeypatch.setattr(cluster_management.subprocess, "run", run)

    def names(self) -> list[str]:
        return [event[0] for event in self.events]


def test_add_worker_falls_back_from_stale_config_address_to_discovered_ipv4(monkeypatch) -> None:
    events = _AddWorkerEvents(monkeypatch)
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

    result = CliRunner().invoke(add_worker, ["unit1"])

    assert result.exit_code == 0, result.output
    assert events.events[0] == ("ssh_setup", ("unit1", "192.168.1.99"), "raspberry")
    assert events.events[1] == ("address", "cluster.addresses", "unit1", "192.168.1.99")
    assert ("copy", "192.168.1.99", ".pioreactor/config.ini") in events.events


def test_add_worker_explicit_address_does_not_try_config_or_discovery(monkeypatch) -> None:
    _AddWorkerEvents(monkeypatch)
    captured_addresses: list[str] = []
    discovery_was_called = False

    def discover_workers_on_network(terminate: bool):
        nonlocal discovery_was_called
        discovery_was_called = True
        return iter([DiscoveredWorker(hostname="unit1", ipv4_address="192.168.1.99")])

    def fake_is_address_on_network(address: str, timeout: float = 10.0) -> bool:
        captured_addresses.append(address)
        return True

    monkeypatch.setattr(cluster_management.config, "get", lambda *_args, **_kwargs: "192.168.1.50")
    monkeypatch.setattr(
        cluster_management.networking,
        "discover_workers_on_network",
        discover_workers_on_network,
    )
    monkeypatch.setattr(cluster_management.networking, "is_address_on_network", fake_is_address_on_network)

    result = CliRunner().invoke(add_worker, ["unit1", "--address", "unit1.local", "-p", "secret"])

    assert result.exit_code == 0, result.output
    assert captured_addresses == ["unit1.local"]
    assert discovery_was_called is False


@pytest.mark.parametrize("selected", [True, False])
def test_add_worker_registers_before_configuring_then_reboots(
    monkeypatch: pytest.MonkeyPatch, selected: bool
) -> None:
    events = _AddWorkerEvents(monkeypatch)
    monkeypatch.setattr(cluster_management, "_find_reachable_worker_add_address", lambda *a: "10.0.0.5")

    args = ["unit1", "-m", "pioreactor_40ml", "-v", "1.5"] if selected else ["unit1"]
    result = CliRunner().invoke(add_worker, args)

    assert result.exit_code == 0, result.output
    assert events.names() == ["ssh_setup", "address", "register", "copy", "join", "reboot"]
    register = events.events[2]
    assert register[1] == {
        "pioreactor_unit": "unit1",
        "model_name": "pioreactor_40ml" if selected else None,
        "model_version": "1.5" if selected else None,
    }
    _, join_command, detached = events.events[4]
    assert detached is False
    assert events.events[5] == ("reboot", "10.0.0.5", True)
    assert join_command.startswith('set -a; . /etc/pioreactor.env; set +a; "$PIO_EXECUTABLE" join-cluster ')
    assert ("--model pioreactor_40ml 1.5" in join_command) is selected


def test_add_worker_failed_join_does_not_reboot(monkeypatch: pytest.MonkeyPatch) -> None:
    events = _AddWorkerEvents(monkeypatch, join_error="Error: Stop activities before changing the model.")
    monkeypatch.setattr(cluster_management, "_find_reachable_worker_add_address", lambda *a: "10.0.0.5")

    result = CliRunner().invoke(add_worker, ["unit1"])

    assert result.exit_code == 1
    assert "Unable to configure unit1: SSH command failed: Error: Stop activities" in result.output
    assert events.names() == ["ssh_setup", "address", "register", "copy", "join"]
