# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager

from pioreactor.temperature_providers import create_temperature_provider
from pioreactor.temperature_providers import LegacyDecayTemperatureProvider
from pioreactor.temperature_providers import register_temperature_provider
from pioreactor.temperature_providers import TemperatureProviderContext
from pioreactor.temperature_providers import TemperatureProviderSchedule
from pioreactor.temperature_providers import unregister_temperature_provider


class _FakeLogger:
    def warning(self, *_args, **_kwargs) -> None:
        return

    def debug(self, *_args, **_kwargs) -> None:
        return

    def error(self, *_args, **_kwargs) -> None:
        return


class _FakePWM:
    def __init__(self) -> None:
        self._locked = False

    def is_locked(self) -> bool:
        return self._locked

    @contextmanager
    def lock_temporarily(self):
        self._locked = True
        try:
            yield
        finally:
            self._locked = False


def test_unknown_provider_name_falls_back_to_legacy_decay() -> None:
    context = TemperatureProviderContext(
        logger=_FakeLogger(),  # type: ignore[arg-type]
        pwm=_FakePWM(),  # type: ignore[arg-type]
        inference_estimator=lambda _features: 1.23,
        read_external_temperature=lambda: 20.0,
        update_heater=lambda _dc: True,
        get_heater_duty_cycle=lambda: 0.0,
        should_exit=lambda: False,
        get_room_temperature=lambda: 22.0,
        inference_n_samples=1,
        inference_samples_every_t_seconds=0.0,
        inference_every_n_seconds=200.0,
    )

    provider = create_temperature_provider("does_not_exist", context)
    assert isinstance(provider, LegacyDecayTemperatureProvider)


def test_can_register_and_create_custom_provider() -> None:
    name = "temperature_provider_test_custom"

    class _CustomProvider:
        @property
        def schedule(self) -> TemperatureProviderSchedule:
            return TemperatureProviderSchedule(interval_seconds=1, run_after_seconds=0.0)

        def infer_temperature(self) -> float | None:
            return 12.34

    register_temperature_provider(name, lambda _context: _CustomProvider())
    try:
        context = TemperatureProviderContext(
            logger=_FakeLogger(),  # type: ignore[arg-type]
            pwm=_FakePWM(),  # type: ignore[arg-type]
            inference_estimator=lambda _features: 1.23,
            read_external_temperature=lambda: 20.0,
            update_heater=lambda _dc: True,
            get_heater_duty_cycle=lambda: 0.0,
            should_exit=lambda: False,
            get_room_temperature=lambda: 22.0,
            inference_n_samples=1,
            inference_samples_every_t_seconds=0.0,
            inference_every_n_seconds=200.0,
        )
        provider = create_temperature_provider(name, context)
        assert provider.infer_temperature() == 12.34
    finally:
        unregister_temperature_provider(name)


def test_legacy_provider_infers_and_restores_heater_dc() -> None:
    heater_dcs: list[float] = []
    current_dc = {"value": 37.0}

    def update_heater(dc: float) -> bool:
        heater_dcs.append(dc)
        current_dc["value"] = dc
        return True

    context = TemperatureProviderContext(
        logger=_FakeLogger(),  # type: ignore[arg-type]
        pwm=_FakePWM(),  # type: ignore[arg-type]
        inference_estimator=lambda features: features["time_series_of_temp"][-1] + 0.5,
        read_external_temperature=lambda: 20.0,
        update_heater=update_heater,
        get_heater_duty_cycle=lambda: current_dc["value"],
        should_exit=lambda: False,
        get_room_temperature=lambda: 22.0,
        inference_n_samples=3,
        inference_samples_every_t_seconds=0.0,
        inference_every_n_seconds=200.0,
    )

    provider = create_temperature_provider("legacy_decay", context)
    assert provider.infer_temperature() == 20.5
    assert heater_dcs == [0, 37.0]
