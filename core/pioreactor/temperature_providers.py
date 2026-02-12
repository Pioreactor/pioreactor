# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t
from dataclasses import dataclass
from time import sleep

from pioreactor import exc
from pioreactor.temperature_inference import TemperatureFeatures
from pioreactor.temperature_inference import TemperatureInferenceEstimator

if t.TYPE_CHECKING:
    from pioreactor.logging import CustomLogger
    from pioreactor.utils.pwm import PWM


class TemperatureProvider(t.Protocol):
    @property
    def schedule(self) -> "TemperatureProviderSchedule": ...

    def infer_temperature(self) -> float | None: ...


@dataclass(frozen=True)
class TemperatureProviderSchedule:
    interval_seconds: int
    run_after_seconds: float
    run_immediately: bool = True


@dataclass(frozen=True)
class TemperatureProviderContext:
    logger: CustomLogger
    pwm: PWM
    inference_estimator: TemperatureInferenceEstimator
    read_external_temperature: t.Callable[[], float]
    update_heater: t.Callable[[float], bool]
    get_heater_duty_cycle: t.Callable[[], float]
    should_exit: t.Callable[[], bool]
    get_room_temperature: t.Callable[[], float]
    inference_n_samples: int
    inference_samples_every_t_seconds: float
    inference_every_n_seconds: float


class TemperatureProviderFactory(t.Protocol):
    def __call__(self, context: TemperatureProviderContext) -> TemperatureProvider: ...


_registered_temperature_providers: dict[str, TemperatureProviderFactory] = {}


def register_temperature_provider(name: str, factory: TemperatureProviderFactory) -> None:
    _registered_temperature_providers[name] = factory


def unregister_temperature_provider(name: str) -> None:
    if name == "legacy_decay":
        raise ValueError("Cannot unregister legacy_decay temperature provider.")
    _registered_temperature_providers.pop(name, None)


def list_registered_temperature_providers() -> list[str]:
    return sorted(_registered_temperature_providers)


def create_temperature_provider(name: str, context: TemperatureProviderContext) -> TemperatureProvider:
    if name not in _registered_temperature_providers:
        context.logger.warning(
            "Unknown temperature provider '%s'. Falling back to 'legacy_decay'. Registered: %s",
            name,
            list_registered_temperature_providers(),
        )
        name = "legacy_decay"

    factory = _registered_temperature_providers[name]
    return factory(context)


class LegacyDecayTemperatureProvider:
    """
    Legacy temperature provider that pauses heating, records a short decay series,
    and then infers liquid temperature from those features.
    """

    def __init__(self, context: TemperatureProviderContext) -> None:
        self._context = context
        inference_total_time = (
            self._context.inference_n_samples * self._context.inference_samples_every_t_seconds
        )
        assert self._context.inference_every_n_seconds > inference_total_time
        self._schedule = TemperatureProviderSchedule(
            interval_seconds=int(self._context.inference_every_n_seconds),
            run_after_seconds=self._context.inference_every_n_seconds - inference_total_time,
            run_immediately=True,
        )

    @property
    def schedule(self) -> TemperatureProviderSchedule:
        return self._schedule

    def infer_temperature(self) -> float | None:
        N_sample_points = self._context.inference_n_samples
        time_between_samples = self._context.inference_samples_every_t_seconds

        assert not self._context.pwm.is_locked(), "PWM is locked - it shouldn't be though!"
        with self._context.pwm.lock_temporarily():
            previous_heater_dc = self._context.get_heater_duty_cycle()
            features: TemperatureFeatures = {
                "previous_heater_dc": previous_heater_dc,
                "room_temp": self._context.get_room_temperature(),
            }

            self._context.update_heater(0)
            time_series_of_temp: list[float] = []

            try:
                for _ in range(N_sample_points):
                    time_series_of_temp.append(self._context.read_external_temperature())
                    sleep(time_between_samples)

                    if self._context.should_exit():
                        previous_heater_dc = 0
                        return None

            except exc.HardwareNotFoundError as error:
                self._context.logger.debug(error, exc_info=True)
                self._context.logger.error(error)
                raise
            finally:
                self._context.update_heater(previous_heater_dc)

        features["time_series_of_temp"] = time_series_of_temp
        self._context.logger.debug(f"{features=}")
        return self._context.inference_estimator(features)


def create_legacy_decay_temperature_provider(
    context: TemperatureProviderContext,
) -> TemperatureProvider:
    return LegacyDecayTemperatureProvider(context)


register_temperature_provider("legacy_decay", create_legacy_decay_temperature_provider)
