# -*- coding: utf-8 -*-
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pioreactor import exc
from pioreactor import pubsub
from pioreactor import whoami


@pytest.fixture
def leader_model_lookup(monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, Any], None, None]:
    """
    Exercise the production (non-testing) model lookup path against a fake leader API.
    """
    workers: dict[str, Any] = {
        "unit1": {"model_name": "pioreactor_40ml", "model_version": "1.5"},
        "unit2": {"model_name": None, "model_version": None},
    }
    requested: list[str] = []

    def fake_get_from_leader(endpoint: str, **kwargs: Any) -> MagicMock:
        requested.append(endpoint)
        response = MagicMock()
        response.json.return_value = workers[endpoint.rsplit("/", 1)[-1]]
        return response

    monkeypatch.setattr(pubsub, "get_from_leader", fake_get_from_leader)
    monkeypatch.setattr(whoami, "is_testing_env", lambda: False)
    monkeypatch.setenv("HOSTNAME", "unit1")
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("MODEL_VERSION", raising=False)

    yield {"workers": workers, "requested": requested}


def test_local_unit_adopts_leader_model_once(leader_model_lookup: dict[str, Any]) -> None:
    requested = leader_model_lookup["requested"]

    model = whoami.get_pioreactor_model()
    assert (model.model_name, model.model_version) == ("pioreactor_40ml", "1.5")
    assert requested == ["/api/workers/unit1"]

    for _ in range(5):
        whoami.get_pioreactor_model()
    assert len(requested) == 1


def test_remote_lookup_always_asks_leader(leader_model_lookup: dict[str, Any]) -> None:
    requested = leader_model_lookup["requested"]

    with pytest.raises(exc.NoModelAssignedError):
        whoami.get_pioreactor_model("unit2")

    leader_model_lookup["workers"]["unit2"] = {"model_name": "pioreactor_40ml", "model_version": "1.5"}
    assert whoami.get_pioreactor_model("unit2").model_name == "pioreactor_40ml"
    assert len(requested) == 2


def test_get_pioreactor_model_prefers_env_for_local_unit(
    leader_model_lookup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_NAME", "pioreactor_20ml")
    monkeypatch.setenv("MODEL_VERSION", "1.1")

    model = whoami.get_pioreactor_model()
    assert (model.model_name, model.model_version) == ("pioreactor_20ml", "1.1")
    assert leader_model_lookup["requested"] == []


def test_get_assigned_experiment_name_retries_transient_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pioreactor.mureq import HTTPException

    attempts: list[str] = []

    def flaky_get_from_leader(endpoint: str, **kwargs: Any) -> MagicMock:
        attempts.append(endpoint)
        if len(attempts) < 3:
            raise HTTPException("connection refused")
        response = MagicMock()
        response.json.return_value = {"experiment": "exp1", "is_active": 1}
        return response

    monkeypatch.setattr(pubsub, "get_from_leader", flaky_get_from_leader)
    monkeypatch.setattr(whoami, "is_testing_env", lambda: False)
    monkeypatch.setattr(whoami.time, "sleep", lambda _: None)
    monkeypatch.delenv("EXPERIMENT", raising=False)

    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    assert len(attempts) == 3


def test_get_assigned_experiment_name_raises_http_exception_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pioreactor.mureq import HTTPException

    attempts: list[str] = []

    def down_get_from_leader(endpoint: str, **kwargs: Any) -> MagicMock:
        attempts.append(endpoint)
        raise HTTPException("connection refused")

    monkeypatch.setattr(pubsub, "get_from_leader", down_get_from_leader)
    monkeypatch.setattr(whoami, "is_testing_env", lambda: False)
    monkeypatch.setattr(whoami.time, "sleep", lambda _: None)
    monkeypatch.delenv("EXPERIMENT", raising=False)

    with pytest.raises(HTTPException):
        whoami.get_assigned_experiment_name("unit1")
    assert len(attempts) == 6


@pytest.fixture(autouse=True)
def isolated_membership_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pioreactor.config import get_config

    monkeypatch.setitem(get_config()["storage"], "persistent_cache", str(tmp_path / "persistent.sqlite"))


@pytest.fixture
def membership_lookup(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("HOSTNAME", "unit1")
    monkeypatch.setattr(whoami, "is_testing_env", lambda: False)
    monkeypatch.setattr(whoami.time, "sleep", lambda _: None)
    monkeypatch.delenv("EXPERIMENT", raising=False)
    monkeypatch.delenv("ACTIVE", raising=False)
    response = MagicMock()
    response.json.return_value = {"experiment": "exp1", "is_active": 0}
    lookup = MagicMock(return_value=response)
    monkeypatch.setattr(pubsub, "get_from_leader", lookup)
    return lookup


def test_membership_falls_back_after_successful_assignment_lookup(
    membership_lookup: MagicMock, caplog: pytest.LogCaptureFixture
) -> None:
    from pioreactor.mureq import HTTPException

    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    membership_lookup.side_effect = HTTPException("connection refused")
    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    assert whoami.is_active("unit1") is False
    assert "leader unreachable" in caplog.text.lower()
    with pytest.raises(HTTPException):
        whoami.get_assigned_experiment_name("unit2")


@pytest.mark.parametrize("lookup_name", ["get_assigned_experiment_name", "is_active"])
def test_membership_404_clears_both_cached_values(membership_lookup: MagicMock, lookup_name: str) -> None:
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    whoami.get_assigned_experiment_name("unit1")
    membership_lookup.return_value.raise_for_status.side_effect = HTTPErrorStatus(404)
    membership_lookup.return_value.json.return_value = {"error": "gone"}
    with pytest.raises((exc.NotAssignedAnExperimentError, exc.NoWorkerFoundError)):
        getattr(whoami, lookup_name)("unit1")
    membership_lookup.side_effect = HTTPException("connection refused")
    for lookup in [whoami.get_assigned_experiment_name, whoami.is_active]:
        with pytest.raises(HTTPException):
            lookup("unit1")


@pytest.mark.parametrize("status", [401, 500])
@pytest.mark.parametrize("lookup_name", ["get_assigned_experiment_name", "is_active"])
def test_membership_http_errors_do_not_use_cache(
    membership_lookup: MagicMock, status: int, lookup_name: str
) -> None:
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    whoami.get_assigned_experiment_name("unit1")
    membership_lookup.return_value.raise_for_status.side_effect = HTTPErrorStatus(status)
    with pytest.raises((HTTPException, ConnectionError)):
        getattr(whoami, lookup_name)("unit1")


def test_membership_leader_and_env_take_precedence(
    membership_lookup: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.mureq import HTTPException

    whoami.get_assigned_experiment_name("unit1")
    membership_lookup.return_value.json.return_value = {"experiment": "exp2", "is_active": 1}
    assert whoami.get_assigned_experiment_name("unit1") == "exp2"
    assert whoami.is_active("unit1") is True
    membership_lookup.side_effect = HTTPException("connection refused")
    monkeypatch.setenv("EXPERIMENT", "override")
    monkeypatch.setenv("ACTIVE", "0")
    membership_lookup.reset_mock()
    assert whoami.get_assigned_experiment_name("unit1") == "override"
    assert whoami.is_active("unit1") is False
    membership_lookup.assert_not_called()
    monkeypatch.delenv("EXPERIMENT")
    monkeypatch.delenv("ACTIVE")
    assert whoami.get_assigned_experiment_name("unit1") == "exp2"
    assert whoami.is_active("unit1") is True


def test_active_lookup_only_refreshes_active_status(membership_lookup: MagicMock) -> None:
    from pioreactor.mureq import HTTPException

    membership_lookup.return_value.json.return_value = {"is_active": 0}
    assert whoami.is_active("unit1") is False
    membership_lookup.side_effect = HTTPException("connection refused")
    assert whoami.is_active("unit1") is False
    with pytest.raises(HTTPException):
        whoami.get_assigned_experiment_name("unit1")


def test_active_refresh_preserves_assignment_timestamp(
    membership_lookup: MagicMock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from pioreactor.mureq import HTTPException
    from pioreactor.utils import timing

    monkeypatch.setattr(timing, "current_utc_timestamp", lambda: "2026-10-11T12:00:00Z")
    whoami.get_assigned_experiment_name("unit1")
    monkeypatch.setattr(timing, "current_utc_timestamp", lambda: "2026-10-11T13:00:00Z")
    membership_lookup.return_value.json.return_value = {"is_active": 1}
    assert whoami.is_active("unit1") is True
    membership_lookup.side_effect = HTTPException("connection refused")
    mqtt_client = MagicMock(side_effect=AssertionError("Fallback logging must stay local"))
    monkeypatch.setattr(pubsub, "create_client", mqtt_client)
    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    assert "from 2026-10-11T12:00:00Z" in caplog.text
    caplog.clear()
    assert whoami.is_active("unit1") is True
    assert "from 2026-10-11T13:00:00Z" in caplog.text
    mqtt_client.assert_not_called()


@pytest.mark.parametrize("lookup_name", ["get_assigned_experiment_name", "is_active"])
def test_remote_lookups_do_not_change_or_use_local_cache(
    membership_lookup: MagicMock, lookup_name: str
) -> None:
    from pioreactor.mureq import HTTPErrorStatus
    from pioreactor.mureq import HTTPException

    whoami.get_assigned_experiment_name("unit1")
    lookup = getattr(whoami, lookup_name)
    membership_lookup.return_value.json.return_value = {"experiment": "remote-exp", "is_active": 1}
    lookup("unit2")
    membership_lookup.side_effect = HTTPException("connection refused")
    with pytest.raises(HTTPException):
        lookup("unit2")
    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    assert whoami.is_active("unit1") is False

    membership_lookup.side_effect = None
    membership_lookup.return_value.raise_for_status.side_effect = HTTPErrorStatus(404)
    membership_lookup.return_value.json.return_value = {"error": "gone"}
    with pytest.raises((exc.NotAssignedAnExperimentError, exc.NoWorkerFoundError)):
        lookup("unit2")
    membership_lookup.side_effect = HTTPException("connection refused")
    assert whoami.get_assigned_experiment_name("unit1") == "exp1"
    assert whoami.is_active("unit1") is False


def test_local_model_survives_leader_loss_and_overrides_env(
    leader_model_lookup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.unit_model import get_local_model

    whoami.get_pioreactor_model()
    assert get_local_model() == ("pioreactor_40ml", "1.5")
    monkeypatch.setattr(pubsub, "get_from_leader", lambda *a, **kw: pytest.fail("must be offline"))
    monkeypatch.setenv("MODEL_NAME", "pioreactor_20ml")
    monkeypatch.setenv("MODEL_VERSION", "1.1")
    assert whoami.get_pioreactor_model().model_name == "pioreactor_40ml"


def test_remote_lookup_does_not_adopt_model(leader_model_lookup: dict[str, Any]) -> None:
    from pioreactor.unit_model import get_local_model

    leader_model_lookup["workers"]["unit2"] = {"model_name": "pioreactor_40ml", "model_version": "1.5"}
    whoami.get_pioreactor_model("unit2")
    assert get_local_model() is None


def test_invalid_leader_model_is_not_persisted(leader_model_lookup: dict[str, Any]) -> None:
    from pioreactor.unit_model import get_local_model

    leader_model_lookup["workers"]["unit1"] = {"model_name": "unknown", "model_version": "1.5"}
    with pytest.raises(exc.UnknownModelAssignedError):
        whoami.get_pioreactor_model()
    assert get_local_model() is None
