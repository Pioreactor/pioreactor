# -*- coding: utf-8 -*-
import sqlite3
from contextlib import closing
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


LEADER_CONFIG = "[cluster.topology]\nleader_hostname=leader\nleader_address=10.0.0.1\n"


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
    shared_config.write_text(LEADER_CONFIG)
    unit_config = tmp_path / "unit_config.ini"
    unit_config.write_text("[cluster.topology]\nleader_address=old.local\n")
    monkeypatch.setenv("GLOBAL_CONFIG", str(shared_config))
    monkeypatch.setenv("LOCAL_CONFIG", str(unit_config))

    mocks = {
        "sudo": Mock(),
        "report": Mock(return_value=True),
        "report_active": Mock(return_value=True),
        "check": Mock(),
        "jobs": MagicMock(),
    }
    monkeypatch.setattr(cluster_membership, "_sudo", mocks["sudo"])
    monkeypatch.setattr(cluster_membership, "JobManager", mocks["jobs"])
    monkeypatch.setattr(cluster_membership, "activities_are_running", lambda: False)
    monkeypatch.setattr(cluster_membership, "report_model_to_leader", mocks["report"])
    monkeypatch.setattr(cluster_membership, "report_active_to_leader", mocks["report_active"])
    monkeypatch.setattr(cluster_membership, "check_model_hardware", mocks["check"])
    return mocks


def test_join_cluster_points_unit_at_leader_and_reports_model(join_env: dict[str, Mock]) -> None:
    cluster_membership.join_cluster(LEADER_CONFIG, 1700000000, "pioreactor_20ml", "1.5")

    join_env["check"].assert_called_once_with("pioreactor_20ml", "1.5")
    assert [call.args[0] for call in join_env["sudo"].call_args_list] == ["date", "tee"]
    assert join_env["sudo"].call_args_list[0].args == ("date", "-u", "--set", "@1700000000")
    assert join_env["sudo"].call_args_list[1].kwargs == {"input": "server 10.0.0.1 iburst prefer\n"}
    assert join_env["report"].call_args.args == ("10.0.0.1", "pioreactor_20ml", "1.5")
    assert join_env["report_active"].call_args.args == ("10.0.0.1", True)
    assert "leader_address" not in cluster_membership.resolve_local_config_path().read_text()


def test_join_cluster_fails_when_the_leader_does_not_get_the_model(join_env: dict[str, Mock]) -> None:
    join_env["report"].return_value = False

    with pytest.raises(RuntimeError, match="Unable to report"):
        cluster_membership.join_cluster(LEADER_CONFIG, 1700000000, "pioreactor_20ml", "1.5")


def test_join_cluster_rejects_unknown_model_before_changing_anything(join_env: dict[str, Mock]) -> None:
    with pytest.raises(UnknownModelAssignedError):
        cluster_membership.join_cluster(LEADER_CONFIG, 1700000000, "unknown", "1.0")

    join_env["sudo"].assert_not_called()
    assert "leader_address=old.local" in cluster_membership.resolve_local_config_path().read_text()


@pytest.fixture
def standalone_env(join_env: dict[str, Mock], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    monkeypatch.setattr(cluster_membership, "get_local_model", lambda: None)
    database = tmp_path / "pioreactor.sqlite"
    unit = get_unit_name()
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE workers (pioreactor_unit TEXT)")
        connection.execute("INSERT INTO workers VALUES (?)", (unit,))
        connection.execute("CREATE TABLE experiment_worker_assignments (pioreactor_unit TEXT)")
    text = (
        f"[cluster.topology]\nleader_hostname={unit}\nleader_address={unit}.local\n"
        f"[mqtt]\nbroker_address={unit}.local\n[storage]\ndatabase={database}\n"
        "[stirring.config]\n# Custom setting\ntarget_rpm=525\n"
    )
    cluster_membership.resolve_global_config_path().write_text(text, encoding="utf-8")
    cluster_membership.standalone_config_path().write_text("stock seed", encoding="utf-8")
    return text


def test_standalone_config_survives_join_retry_and_leave(standalone_env: str) -> None:
    shared = cluster_membership.resolve_global_config_path()
    saved = cluster_membership.standalone_config_path()
    cluster_membership.join_cluster(LEADER_CONFIG, 1700000000)
    cluster_membership.join_cluster(LEADER_CONFIG, 1700000000)
    assert shared.read_text(encoding="utf-8") == LEADER_CONFIG
    assert saved.read_text(encoding="utf-8") == standalone_env

    assert cluster_membership.leave_cluster()
    assert not cluster_membership.leave_cluster()
    assert shared.read_text(encoding="utf-8") == standalone_env
    unit_config = ConfigParserMod(strict=False)
    unit_config.read(cluster_membership.resolve_local_config_path())
    assert unit_config.get("cluster.topology", "leader_address") == "127.0.0.1"
    assert unit_config.get("mqtt", "broker_address") == "127.0.0.1"


@pytest.mark.parametrize(
    "statement, message",
    [
        ("INSERT INTO workers VALUES ('another-unit')", "Remove this unit's workers"),
        ("INSERT INTO experiment_worker_assignments SELECT pioreactor_unit FROM workers", "Unassign"),
    ],
)
def test_busy_standalone_rejects_join_without_overwriting_config(
    standalone_env: str, tmp_path: Path, statement: str, message: str
) -> None:
    with closing(sqlite3.connect(tmp_path / "pioreactor.sqlite")) as connection, connection:
        connection.execute(statement)
    with pytest.raises(RuntimeError, match=message):
        cluster_membership.join_cluster(LEADER_CONFIG, 1700000000)
    assert cluster_membership.resolve_global_config_path().read_text(encoding="utf-8") == standalone_env
    assert cluster_membership.standalone_config_path().read_text(encoding="utf-8") == "stock seed"


def test_standalone_join_keeps_saved_config_when_report_fails(
    standalone_env: str, join_env: dict[str, Mock]
) -> None:
    join_env["report_active"].return_value = False
    with pytest.raises(RuntimeError, match="Unable to report"):
        cluster_membership.join_cluster(LEADER_CONFIG, 1700000000)
    assert cluster_membership.resolve_global_config_path().read_text(encoding="utf-8") == LEADER_CONFIG
    assert cluster_membership.standalone_config_path().read_text(encoding="utf-8") == standalone_env


def test_join_cli_reads_the_staged_config(
    join_env: dict[str, Mock], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cluster_membership, "get_local_model", lambda: None)
    staged = tmp_path / ".incoming-config.ini"
    staged.write_text(LEADER_CONFIG, encoding="utf-8")

    result = CliRunner().invoke(
        pio, ["cluster", "join", "--leader-time", "1", "--staged-config", str(staged)]
    )

    assert result.exit_code == 0, result.output
    assert not cluster_membership.standalone_config_path().exists()
    join_env["report_active"].assert_called_once_with("10.0.0.1", True)


def test_existing_leader_worker_leaves_to_seeded_config(
    join_env: dict[str, Mock], monkeypatch: pytest.MonkeyPatch
) -> None:
    template = Path(__file__).parents[2] / "packaging/shared-assets/pioreactor/config.example.ini"
    cluster_membership.standalone_config_path().write_bytes(template.read_bytes())
    cluster_membership.leave_cluster()
    active = ConfigParserMod(strict=False)
    active.read(cluster_membership.resolve_global_config_path())
    assert active.get("cluster.topology", "leader_hostname") == get_unit_name()
    assert active.get("mqtt", "broker_address") == f"{get_unit_name()}.local"
    assert cluster_membership.standalone_config_path().read_bytes() == template.read_bytes()


def test_joining_from_another_leader_is_rejected(join_env: dict[str, Mock]) -> None:
    incoming = LEADER_CONFIG.replace("leader_hostname=leader", "leader_hostname=another")
    with pytest.raises(RuntimeError, match="Leave that cluster first"):
        cluster_membership.join_cluster(incoming, 1700000000)
    assert cluster_membership.resolve_global_config_path().read_text(encoding="utf-8") == LEADER_CONFIG


def test_leave_cluster_undoes_join_and_can_run_twice(join_env: dict[str, Mock]) -> None:
    shared_config = cluster_membership.resolve_global_config_path()
    unit_config = cluster_membership.resolve_local_config_path()

    cluster_membership.leave_cluster()
    cluster_membership.leave_cluster()

    assert not shared_config.exists()
    assert unit_config.exists()
    join_env["jobs"].return_value.__enter__.return_value.kill_jobs.assert_called_with(all_jobs=True)
    join_env["sudo"].assert_called_with("rm", "-f", str(cluster_membership.CHRONY_LEADER_SOURCE))


def test_leave_cluster_is_a_noop_on_the_leader(join_env: dict[str, Mock]) -> None:
    shared_config = cluster_membership.resolve_global_config_path()
    shared_config.write_text(f"[cluster.topology]\nleader_hostname={get_unit_name()}\nleader_address=x\n")

    assert not cluster_membership.leave_cluster(stop_activities=True)

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
        "leave": Mock(return_value=True),
        "run": Mock(),
    }
    monkeypatch.setattr("pioreactor.pubsub.delete_from_leader", mocks["delete"])
    monkeypatch.setattr("pioreactor.cluster_membership.leave_cluster", mocks["leave"])
    monkeypatch.setattr("pioreactor.cluster_membership.activities_are_running", lambda: False)
    shared_config = ConfigParserMod()
    shared_config.read_string(LEADER_CONFIG)
    monkeypatch.setattr("pioreactor.cluster_membership._read_shared_config", lambda: shared_config)
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
