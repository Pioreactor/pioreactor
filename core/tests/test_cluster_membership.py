# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from pioreactor import cluster_membership
from pioreactor.cli.pio import pio
from pioreactor.config import ConfigParserMod
from pioreactor.exc import UnknownModelAssignedError
from pioreactor.mureq import HTTPException
from pioreactor.mureq import Response
from pioreactor.whoami import get_unit_name


@pytest.mark.parametrize(
    "broker_address, broker_removed",
    [("old.local", True), ("localhost", False)],
)
def test_clear_previous_leader_overrides(tmp_path: Path, broker_address: str, broker_removed: bool) -> None:
    unit_config = tmp_path / "unit_config.ini"
    unit_config.write_text(
        "[cluster.topology]\n"
        "leader_hostname=old\n"
        "leader_address=old.local\n"
        "\n"
        "[mqtt]\n"
        f"broker_address={broker_address}\n"
        "\n"
        "[stirring.config]\n"
        "# a comment\n"
        "target_rpm=500\n"
    )

    cluster_membership.clear_previous_leader_overrides(unit_config)

    text = unit_config.read_text()
    assert "leader_" not in text
    assert (f"broker_address={broker_address}" in text) is not broker_removed
    assert "# a comment\ntarget_rpm=500\n" in text


@pytest.fixture
def join_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    shared_config = tmp_path / "config.ini"
    shared_config.write_text("[cluster.topology]\nleader_hostname=leader\nleader_address=10.0.0.1\n")
    unit_config = tmp_path / "unit_config.ini"
    unit_config.write_text("[cluster.topology]\nleader_address=old.local\n")
    monkeypatch.setenv("GLOBAL_CONFIG", str(shared_config))
    monkeypatch.setenv("LOCAL_CONFIG", str(unit_config))

    mocks = {
        "sudo": Mock(),
        "report": Mock(return_value=True),
        "check": Mock(),
        "jobs": MagicMock(),
    }
    monkeypatch.setattr(cluster_membership, "_sudo", mocks["sudo"])
    monkeypatch.setattr(cluster_membership, "JobManager", mocks["jobs"])
    monkeypatch.setattr(cluster_membership, "activities_are_running", lambda: False)
    monkeypatch.setattr(cluster_membership, "report_model_to_leader", mocks["report"])
    monkeypatch.setattr(cluster_membership, "check_model_hardware", mocks["check"])
    return mocks


def test_join_cluster_points_unit_at_leader_and_reports_model(join_env: dict[str, Mock]) -> None:
    cluster_membership.join_cluster(1700000000, "pioreactor_20ml", "1.5")

    join_env["check"].assert_called_once_with("pioreactor_20ml", "1.5")
    assert [call.args[0] for call in join_env["sudo"].call_args_list] == ["date", "tee"]
    assert join_env["sudo"].call_args_list[0].args == ("date", "-u", "--set", "@1700000000")
    assert join_env["sudo"].call_args_list[1].kwargs == {"input": "server 10.0.0.1 iburst prefer\n"}
    join_env["report"].assert_called_once_with("10.0.0.1", "pioreactor_20ml", "1.5")
    assert "leader_address" not in cluster_membership.resolve_local_config_path().read_text()


def test_join_cluster_fails_when_the_leader_does_not_get_the_model(join_env: dict[str, Mock]) -> None:
    join_env["report"].return_value = False

    with pytest.raises(RuntimeError, match="Unable to report"):
        cluster_membership.join_cluster(1700000000, "pioreactor_20ml", "1.5")


def test_join_cluster_rejects_unknown_model_before_changing_anything(join_env: dict[str, Mock]) -> None:
    with pytest.raises(UnknownModelAssignedError):
        cluster_membership.join_cluster(1700000000, "unknown", "1.0")

    join_env["sudo"].assert_not_called()
    assert "leader_address=old.local" in cluster_membership.resolve_local_config_path().read_text()


def test_leave_cluster_undoes_join_and_can_run_twice(join_env: dict[str, Mock]) -> None:
    shared_config = cluster_membership.resolve_global_config_path()
    unit_config = cluster_membership.resolve_local_config_path()

    cluster_membership.leave_cluster()
    cluster_membership.leave_cluster()

    assert not shared_config.exists()
    assert unit_config.exists()
    join_env["jobs"].return_value.__enter__.return_value.kill_jobs.assert_called_with(all_jobs=True)
    join_env["sudo"].assert_called_with("rm", "-f", str(cluster_membership.CHRONY_LEADER_SOURCE))


def test_leave_cluster_refuses_on_the_leader(join_env: dict[str, Mock]) -> None:
    shared_config = cluster_membership.resolve_global_config_path()
    shared_config.write_text(f"[cluster.topology]\nleader_hostname={get_unit_name()}\nleader_address=x\n")

    with pytest.raises(RuntimeError, match="leader"):
        cluster_membership.leave_cluster(stop_activities=True)

    assert shared_config.exists()
    join_env["sudo"].assert_not_called()


def test_leave_cluster_asks_for_activities_to_be_stopped_first(
    join_env: dict[str, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cluster_membership, "activities_are_running", lambda: True)

    with pytest.raises(RuntimeError, match="Stop activities"):
        cluster_membership.leave_cluster()
    assert cluster_membership.resolve_global_config_path().exists()

    cluster_membership.leave_cluster(stop_activities=True)
    assert not cluster_membership.resolve_global_config_path().exists()


@pytest.fixture
def leave_cli(monkeypatch: pytest.MonkeyPatch) -> dict[str, Mock]:
    mocks = {
        "delete": Mock(return_value=Response("http://leader/api/workers", 202, {}, b"{}")),
        "leave": Mock(),
        "run": Mock(),
    }
    monkeypatch.setattr("pioreactor.pubsub.delete_from_leader", mocks["delete"])
    monkeypatch.setattr("pioreactor.cluster_membership.leave_cluster", mocks["leave"])
    monkeypatch.setattr("pioreactor.cluster_membership.activities_are_running", lambda: False)
    monkeypatch.setattr("pioreactor.cluster_membership._read_shared_config", ConfigParserMod)
    monkeypatch.setattr("pioreactor.cli.cluster.subprocess.run", mocks["run"])
    return mocks


def test_cluster_leave_tells_the_leader_then_leaves_and_reboots(leave_cli: dict[str, Mock]) -> None:
    result = CliRunner().invoke(pio, ["cluster", "leave", "-y"])

    assert result.exit_code == 0, result.output
    leave_cli["delete"].assert_called_once_with(f"/api/workers/{get_unit_name()}")
    leave_cli["leave"].assert_called_once_with()
    leave_cli["run"].assert_called_once_with(["sudo", "reboot"])


def test_cluster_leave_still_leaves_when_the_leader_is_unreachable(leave_cli: dict[str, Mock]) -> None:
    leave_cli["delete"].side_effect = HTTPException("offline")

    result = CliRunner().invoke(pio, ["cluster", "leave", "-y"])

    assert result.exit_code == 0, result.output
    assert "Leaving anyway." in result.output
    leave_cli["leave"].assert_called_once_with()


def test_cluster_leave_refuses_while_activities_run(
    leave_cli: dict[str, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pioreactor.cluster_membership.activities_are_running", lambda: True)

    result = CliRunner().invoke(pio, ["cluster", "leave", "-y"])

    assert result.exit_code == 1
    assert "Stop activities before leaving the cluster." in result.output
    leave_cli["delete"].assert_not_called()
    leave_cli["leave"].assert_not_called()


def test_cluster_leave_on_the_leader_refuses_before_telling_the_leader(
    leave_cli: dict[str, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_config = ConfigParserMod()
    shared_config.read_dict({"cluster.topology": {"leader_hostname": get_unit_name()}})
    monkeypatch.setattr("pioreactor.cluster_membership._read_shared_config", lambda: shared_config)

    result = CliRunner().invoke(pio, ["cluster", "leave", "-y"])

    assert result.exit_code == 1
    assert "leader" in result.output
    leave_cli["delete"].assert_not_called()
    leave_cli["leave"].assert_not_called()
