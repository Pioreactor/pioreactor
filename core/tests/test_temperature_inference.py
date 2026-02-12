# -*- coding: utf-8 -*-
from pioreactor.models import PIOREACTOR_20ml__v1_0
from pioreactor.models import PIOREACTOR_20ml__v1_1
from pioreactor.models import PIOREACTOR_40ml__v1_0
from pioreactor.temperature_inference import create_temperature_inference_estimator
from pioreactor.temperature_inference import get_legacy_temperature_estimator_for_model
from pioreactor.temperature_inference import infer_temperature_legacy_20_1_0
from pioreactor.temperature_inference import infer_temperature_legacy_20_2_0
from pioreactor.temperature_inference import register_temperature_inference_estimator
from pioreactor.temperature_inference import unregister_temperature_inference_estimator


def test_router_selects_legacy_20_1_0_for_20ml_v1_0() -> None:
    estimator = get_legacy_temperature_estimator_for_model(PIOREACTOR_20ml__v1_0)
    assert estimator is infer_temperature_legacy_20_1_0


def test_router_selects_legacy_20_2_0_for_20ml_v1_1() -> None:
    estimator = get_legacy_temperature_estimator_for_model(PIOREACTOR_20ml__v1_1)
    assert estimator is infer_temperature_legacy_20_2_0


def test_router_selects_legacy_20_2_0_for_40ml() -> None:
    estimator = get_legacy_temperature_estimator_for_model(PIOREACTOR_40ml__v1_0)
    assert estimator is infer_temperature_legacy_20_2_0


def test_unknown_estimator_name_falls_back_to_legacy() -> None:
    estimator = create_temperature_inference_estimator(
        "does_not_exist",
        model=PIOREACTOR_20ml__v1_0,
    )
    assert estimator is infer_temperature_legacy_20_1_0


def test_can_register_and_create_custom_estimator() -> None:
    name = "temp_test_custom"

    def custom_estimator(_features: dict[str, object]) -> float:
        return 12.34

    def custom_factory(*, model: object, logger: object | None = None):  # noqa: ARG001
        return custom_estimator

    register_temperature_inference_estimator(name, custom_factory)
    try:
        estimator = create_temperature_inference_estimator(name, model=PIOREACTOR_40ml__v1_0)
        assert estimator({"any": 1.0}) == 12.34
    finally:
        unregister_temperature_inference_estimator(name)
