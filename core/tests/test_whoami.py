# -*- coding: utf-8 -*-
from collections.abc import Generator
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
    whoami.clear_pioreactor_model_cache()

    yield {"workers": workers, "requested": requested}

    whoami.clear_pioreactor_model_cache()


def test_get_pioreactor_model_uses_one_leader_request_and_caches(leader_model_lookup: dict[str, Any]) -> None:
    requested = leader_model_lookup["requested"]

    model = whoami.get_pioreactor_model()
    assert (model.model_name, model.model_version) == ("pioreactor_40ml", "1.5")
    assert requested == ["/api/workers/unit1"]

    for _ in range(5):
        whoami.get_pioreactor_model()
    assert len(requested) == 1


def test_get_pioreactor_model_cache_expires(leader_model_lookup: dict[str, Any]) -> None:
    requested = leader_model_lookup["requested"]

    whoami.get_pioreactor_model()
    cached_at, name, version = whoami._model_from_leader_cache["unit1"]
    whoami._model_from_leader_cache["unit1"] = (
        cached_at - whoami._MODEL_FROM_LEADER_TTL_SECONDS - 1,
        name,
        version,
    )
    leader_model_lookup["workers"]["unit1"] = {"model_name": "pioreactor_20ml", "model_version": "1.1"}

    model = whoami.get_pioreactor_model()
    assert (model.model_name, model.model_version) == ("pioreactor_20ml", "1.1")
    assert len(requested) == 2


def test_get_pioreactor_model_does_not_cache_unassigned_models(leader_model_lookup: dict[str, Any]) -> None:
    requested = leader_model_lookup["requested"]

    for _ in range(2):
        with pytest.raises(exc.NoModelAssignedError):
            whoami.get_pioreactor_model("unit2")
    assert len(requested) == 2

    leader_model_lookup["workers"]["unit2"] = {"model_name": "pioreactor_40ml", "model_version": "1.5"}
    assert whoami.get_pioreactor_model("unit2").model_name == "pioreactor_40ml"


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
        response.json.return_value = {"experiment": "exp1"}
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
