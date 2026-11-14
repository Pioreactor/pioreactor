# -*- coding: utf-8 -*-
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from pioreactor import exc
from pioreactor import pubsub
from pioreactor import whoami


@pytest.fixture(autouse=True)
def isolated_persistent_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pioreactor.config import get_config

    monkeypatch.setitem(get_config()["storage"], "persistent_cache", str(tmp_path / "persistent.sqlite"))


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


def test_local_lookup_never_asks_the_leader(leader_model_lookup: dict[str, Any]) -> None:
    from pioreactor.unit_model import get_local_model

    with pytest.raises(exc.NoModelAssignedError):
        whoami.get_pioreactor_model()
    assert leader_model_lookup["requested"] == []
    assert get_local_model() is None


def test_adopt_leader_model_saves_once(leader_model_lookup: dict[str, Any]) -> None:
    from pioreactor.unit_model import adopt_leader_model

    requested = leader_model_lookup["requested"]
    assert adopt_leader_model() == ("pioreactor_40ml", "1.5")
    assert requested == ["/api/workers/unit1"]

    leader_model_lookup["workers"]["unit1"] = {"model_name": "pioreactor_20ml", "model_version": "1.5"}
    assert adopt_leader_model() == ("pioreactor_40ml", "1.5")
    for _ in range(5):
        assert whoami.get_pioreactor_model().model_name == "pioreactor_40ml"
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


def test_local_model_survives_leader_loss_and_overrides_env(
    leader_model_lookup: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    from pioreactor.unit_model import adopt_leader_model
    from pioreactor.unit_model import get_local_model

    adopt_leader_model()
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
    from pioreactor.unit_model import adopt_leader_model
    from pioreactor.unit_model import get_local_model

    leader_model_lookup["workers"]["unit1"] = {"model_name": "unknown", "model_version": "1.5"}
    with pytest.raises(exc.UnknownModelAssignedError):
        adopt_leader_model()
    assert get_local_model() is None


def test_assigned_experiment_from_leader_ignores_experiment_env(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_get_from_leader(endpoint: str, **kwargs: Any) -> MagicMock:
        assert endpoint == "/api/workers/unit2/experiment"
        response = MagicMock()
        response.json.return_value = {"experiment": "exp-from-leader"}
        return response

    monkeypatch.setattr(pubsub, "get_from_leader", fake_get_from_leader)
    monkeypatch.setenv("EXPERIMENT", "exp-from-env")

    assert whoami.get_assigned_experiment_name("unit2") == "exp-from-env"
    assert whoami.get_assigned_experiment_name_from_leader("unit2") == "exp-from-leader"
