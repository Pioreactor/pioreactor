# -*- coding: utf-8 -*-
from pathlib import Path
from unittest.mock import Mock

import pytest
from pioreactor import cluster_membership
from pioreactor.exc import UnknownModelAssignedError


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
    }
    monkeypatch.setattr(cluster_membership, "_sudo", mocks["sudo"])
    monkeypatch.setattr(cluster_membership, "report_model_to_leader", mocks["report"])
    monkeypatch.setattr("pioreactor.web.tasks.check_model_hardware", mocks["check"])
    return mocks


def test_join_cluster_points_unit_at_leader_and_reports_model(join_env: dict[str, Mock]) -> None:
    model = cluster_membership.join_cluster(1700000000, ("pioreactor_20ml", "1.5"))

    assert model == ("pioreactor_20ml", "1.5")
    join_env["check"].call_local.assert_called_once_with("pioreactor_20ml", "1.5")
    assert [call.args[0] for call in join_env["sudo"].call_args_list] == ["date", "tee"]
    assert join_env["sudo"].call_args_list[0].args == ("date", "-u", "--set", "@1700000000")
    assert join_env["sudo"].call_args_list[1].kwargs == {"input": "server 10.0.0.1 iburst prefer\n"}
    join_env["report"].assert_called_once_with("10.0.0.1", "pioreactor_20ml", "1.5")
    assert "leader_address" not in cluster_membership.resolve_local_config_path().read_text()


def test_join_cluster_fails_when_the_leader_does_not_get_the_model(join_env: dict[str, Mock]) -> None:
    join_env["report"].return_value = False

    with pytest.raises(RuntimeError, match="Unable to report"):
        cluster_membership.join_cluster(1700000000, ("pioreactor_20ml", "1.5"))


def test_join_cluster_rejects_unknown_model_before_changing_anything(join_env: dict[str, Mock]) -> None:
    with pytest.raises(UnknownModelAssignedError):
        cluster_membership.join_cluster(1700000000, ("unknown", "1.0"))

    join_env["sudo"].assert_not_called()
    assert "leader_address=old.local" in cluster_membership.resolve_local_config_path().read_text()
