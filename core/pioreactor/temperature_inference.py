# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

if t.TYPE_CHECKING:
    from pioreactor.logging import CustomLogger
    from pioreactor.structs import Model

type TemperatureFeatures = dict[str, t.Any]


class TemperatureInferenceEstimator(t.Protocol):
    def __call__(self, features: TemperatureFeatures) -> float: ...


class TemperatureInferenceEstimatorFactory(t.Protocol):
    def __call__(
        self,
        *,
        model: Model,
        logger: CustomLogger | None = None,
    ) -> TemperatureInferenceEstimator: ...


_registered_temperature_inference_estimators: dict[str, TemperatureInferenceEstimatorFactory] = {}


def register_temperature_inference_estimator(
    name: str, factory: TemperatureInferenceEstimatorFactory
) -> None:
    _registered_temperature_inference_estimators[name] = factory


def unregister_temperature_inference_estimator(name: str) -> None:
    if name == "legacy":
        raise ValueError("Cannot unregister legacy temperature estimator.")
    _registered_temperature_inference_estimators.pop(name, None)


def list_registered_temperature_inference_estimators() -> list[str]:
    return sorted(_registered_temperature_inference_estimators)


def create_temperature_inference_estimator(
    name: str,
    *,
    model: Model,
    logger: CustomLogger | None = None,
) -> TemperatureInferenceEstimator:
    if name not in _registered_temperature_inference_estimators:
        if logger is not None:
            logger.warning(
                "Unknown temperature estimator '%s'. Falling back to 'legacy'. Registered: %s",
                name,
                list_registered_temperature_inference_estimators(),
            )
        name = "legacy"

    factory = _registered_temperature_inference_estimators[name]
    return factory(model=model, logger=logger)


def get_legacy_temperature_estimator_for_model(
    model: Model,
    logger: CustomLogger | None = None,
) -> TemperatureInferenceEstimator:
    if model.model_name.startswith("pioreactor_20ml"):
        if model.model_version == "1.0":
            return infer_temperature_legacy_20_1_0
        return infer_temperature_legacy_20_2_0

    if model.model_name.startswith("pioreactor_40ml"):
        return infer_temperature_legacy_20_2_0

    if logger is not None:
        logger.warning("Approximating temperature inference for non-pioreactor models using pioreactor_40ml.")
    return infer_temperature_legacy_20_2_0


def create_legacy_temperature_inference_estimator(
    *,
    model: Model,
    logger: CustomLogger | None = None,
) -> TemperatureInferenceEstimator:
    return get_legacy_temperature_estimator_for_model(model=model, logger=logger)


def infer_temperature_legacy_20_1_0(features: TemperatureFeatures) -> float:
    """
    Legacy estimator used by the v1.0 20mL model.
    """
    if features["previous_heater_dc"] == 0:
        return features["time_series_of_temp"][-1]

    import numpy as np
    from numpy import exp

    times_series = features["time_series_of_temp"]
    room_temp = features["room_temp"]
    n = len(times_series)
    y = np.array(times_series) - room_temp
    x = np.arange(n)

    # First regression
    S = np.zeros(n)
    SS = np.zeros(n)
    for i in range(1, n):
        S[i] = S[i - 1] + 0.5 * (y[i - 1] + y[i]) * (x[i] - x[i - 1])
        SS[i] = SS[i - 1] + 0.5 * (S[i - 1] + S[i]) * (x[i] - x[i - 1])

    A_penalizer, A_prior = 100.0, -0.0012
    B_penalizer, B_prior = 50.0, -0.325

    M1 = np.array(
        [
            [
                (SS**2).sum() + A_penalizer,
                (SS * S).sum(),
                (SS * x).sum(),
                (SS).sum(),
            ],
            [(SS * S).sum(), (S**2).sum() + B_penalizer, (S * x).sum(), (S).sum()],
            [(SS * x).sum(), (S * x).sum(), (x**2).sum(), (x).sum()],
            [(SS).sum(), (S).sum(), (x).sum(), n],
        ]
    )
    Y1 = np.array(
        [
            (y * SS).sum() + A_penalizer * A_prior,
            (y * S).sum() + B_penalizer * B_prior,
            (y * x).sum(),
            y.sum(),
        ]
    )

    try:
        A, B, _, _ = np.linalg.solve(M1, Y1)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"Error in temperature inference. {x=}, {y=}") from exc

    if (B**2 + 4 * A) < 0:
        raise ValueError(f"Error in temperature inference. {x=}, {y=}")

    p = 0.5 * (B + np.sqrt(B**2 + 4 * A))
    q = 0.5 * (B - np.sqrt(B**2 + 4 * A))

    # Second regression
    M2 = np.array(
        [
            [exp(2 * p * x).sum(), exp((p + q) * x).sum()],
            [exp((q + p) * x).sum(), exp(2 * q * x).sum()],
        ]
    )
    Y2 = np.array([(y * exp(p * x)).sum(), (y * exp(q * x)).sum()])

    try:
        b, _ = np.linalg.solve(M2, Y2)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"Error in temperature inference. {x=}, {y=}") from exc

    alpha, beta = b, p
    return float(room_temp + alpha * exp(beta * n))


def infer_temperature_legacy_20_2_0(features: TemperatureFeatures) -> float:
    """
    Legacy linear estimator used by >=1.1 models.
    """
    if features["previous_heater_dc"] == 0:
        return features["time_series_of_temp"][-1]

    X = [features["previous_heater_dc"]] + features["time_series_of_temp"]
    X = [x / 35.0 for x in X]
    X.append(X[1] ** 2)
    X.append(X[20] * X[0])

    coefs = [
        -1.37221255e01,
        1.50807347e02,
        1.52808570e01,
        -7.17124615e01,
        -8.15352596e01,
        -5.82053398e01,
        -8.49915201e01,
        -3.69729300e01,
        -8.51994806e-02,
        1.12635670e01,
        3.37434235e01,
        3.36348041e01,
        4.25731033e01,
        6.72551219e01,
        8.37883314e01,
        6.29508694e01,
        4.95735854e01,
        1.86594862e01,
        3.12848519e-01,
        -3.82815596e01,
        -5.62834504e01,
        -9.27840943e01,
        -7.62113224e00,
        8.18877406e00,
    ]

    intercept = -6.171633633597331
    return _dot_product(coefs, X) + intercept


def _dot_product(vec1: list[float], vec2: list[float]) -> float:
    if len(vec1) != len(vec2):
        raise ValueError(f"Vectors must be of the same length. Got {len(vec1)=}, {len(vec2)=}")
    return sum(x * y for x, y in zip(vec1, vec2))


register_temperature_inference_estimator("legacy", create_legacy_temperature_inference_estimator)
