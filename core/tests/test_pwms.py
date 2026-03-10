# -*- coding: utf-8 -*-
# test_pwms
import json
import logging
import signal
import sys
import time
import types
from typing import Any

import pytest
from pioreactor import pubsub
from pioreactor.exc import PWMError
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import pwm as pwm_module
from pioreactor.utils.pwm import PWM
from pioreactor.utils.pwm import SoftwarePWMOutputDevice
from pioreactor.whoami import get_unit_name


def pause(n=1) -> None:
    time.sleep(n * 0.25)


def test_updates_cache() -> None:
    exp = "test_updates_cache"
    unit = get_unit_name()

    pwm12 = PWM(12, 10, experiment=exp, unit=unit)
    pwm12.lock()
    pwm12.start(50)

    with local_intermittent_storage("pwm_dc") as cache:
        assert cache[12] == 50

    pwm12.change_duty_cycle(20)

    with local_intermittent_storage("pwm_dc") as cache:
        assert cache[12] == 20

    pwm12.change_duty_cycle(0)

    with local_intermittent_storage("pwm_dc") as cache:
        assert 12 not in cache

    pwm12.clean_up()


def test_pwm_update_mqtt() -> None:
    exp = "test_pwm_update_mqtt"
    unit = get_unit_name()

    mqtt_items = []

    def collect(msg) -> None:
        mqtt_items.append(msg.payload.decode())

    pubsub.subscribe_and_callback(collect, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)

    pwm12 = PWM(12, 10, experiment=exp, unit=unit)
    pwm12.lock()
    pwm12.start(50)
    pwm12.change_duty_cycle(20)
    pwm12.clean_up()
    pause()

    assert len(mqtt_items) == 3
    assert json.loads(mqtt_items[0])["12"] == 50.0
    assert json.loads(mqtt_items[1])["12"] == 20.0
    with pytest.raises(KeyError):
        # we don't publish 0.0
        assert json.loads(mqtt_items[2])["12"] == 0.0


def test_pwm_update_mqtt_multiple_at_one() -> None:
    exp = "test_pwm_update_mqtt_multiple_at_one"
    unit = get_unit_name()

    mqtt_items = []

    def collect(msg) -> None:
        mqtt_items.append(msg.payload.decode())

    pubsub.subscribe_and_callback(collect, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)

    pwm12 = PWM(12, 10, experiment=exp, unit=unit)
    pwm12.lock()
    pwm12.start(50)

    pwm17 = PWM(17, 10, experiment=exp, unit=unit)
    pwm17.lock()
    pwm17.start(34)
    pwm17.change_duty_cycle(20)

    pwm17.clean_up()
    pwm12.clean_up()

    pause()

    assert len(mqtt_items) == 5
    assert json.loads(mqtt_items[0])["12"] == 50.0
    assert json.loads(mqtt_items[0]).get("17", 0.0) == 0.0

    assert json.loads(mqtt_items[1]).get("17", 0.0) == 34.0
    assert json.loads(mqtt_items[1]).get("12", 0.0) == 50.0

    assert json.loads(mqtt_items[-1]).get("17", 0.0) == 0.0
    assert json.loads(mqtt_items[-1]).get("12", 0.0) == 0.0


def _install_fake_lgpio(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    fake_lgpio: Any = types.ModuleType("lgpio")

    class FakeLgpioError(Exception):
        pass

    state: dict[str, Any] = {
        "raise_when_dc": None,
        "raise_when_write": None,
        "tx_calls": [],
        "write_calls": [],
    }

    def gpiochip_open(_chip: int) -> int:
        return 1

    def gpio_claim_output(_handle: int, _pin: int) -> None:
        return

    def tx_pwm(_handle: int, _pin: int, _frequency: float, duty_cycle: float) -> None:
        tx_calls = state["tx_calls"]
        assert isinstance(tx_calls, list)
        tx_calls.append(duty_cycle)

        raise_when_dc = state["raise_when_dc"]
        if (raise_when_dc is not None) and (duty_cycle == raise_when_dc):
            raise FakeLgpioError("simulated lgpio tx_pwm failure")

    def gpio_write(_handle: int, _pin: int, level: int) -> None:
        write_calls = state["write_calls"]
        assert isinstance(write_calls, list)
        write_calls.append(float(level))

        raise_when_write = state["raise_when_write"]
        if (raise_when_write is not None) and (float(level) == raise_when_write):
            raise FakeLgpioError("simulated lgpio gpio_write failure")

    def gpiochip_close(_handle: int) -> None:
        return

    fake_lgpio.error = FakeLgpioError
    fake_lgpio.gpiochip_open = gpiochip_open
    fake_lgpio.gpio_claim_output = gpio_claim_output
    fake_lgpio.tx_pwm = tx_pwm
    fake_lgpio.gpio_write = gpio_write
    fake_lgpio.gpiochip_close = gpiochip_close

    monkeypatch.setitem(sys.modules, "lgpio", fake_lgpio)
    return state


def test_software_pwm_dc_errors_raise_pwm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    pwm = SoftwarePWMOutputDevice(pin=17, frequency=100)
    pwm.start(0)

    state["raise_when_dc"] = 25.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.dc = 25.0

    assert pwm.dc == 0.0


def test_software_pwm_stop_errors_raise_pwm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    pwm = SoftwarePWMOutputDevice(pin=17, frequency=100)
    pwm.start(20)

    state["raise_when_dc"] = 0.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.off()


def test_software_pwm_close_forces_low_even_if_stop_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    pwm = SoftwarePWMOutputDevice(pin=17, frequency=100)
    pwm.start(20)

    state["raise_when_dc"] = 0.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.off()

    assert pwm.dc == 20.0
    pwm.close()

    write_calls = state["write_calls"]
    assert isinstance(write_calls, list)
    assert write_calls[-1] == 0.0
    assert pwm.dc == 0.0


def test_software_pwm_close_warns_and_keeps_dc_if_force_low_fails(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    state = _install_fake_lgpio(monkeypatch)
    pwm = SoftwarePWMOutputDevice(pin=17, frequency=100)
    pwm.start(20)

    state["raise_when_dc"] = 0.0
    state["raise_when_write"] = 0.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.off()

    assert pwm.dc == 20.0

    with caplog.at_level(logging.WARNING, logger="pwm"):
        pwm.close()

    assert pwm.dc == 20.0
    assert any(
        "Unable to confirm GPIO-17 low during software PWM close" in record.message
        for record in caplog.records
    )


def test_software_pwm_close_infos_if_pwm_stops_but_low_unconfirmed(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    state = _install_fake_lgpio(monkeypatch)
    pwm = SoftwarePWMOutputDevice(pin=17, frequency=100)
    pwm.start(20)

    state["raise_when_write"] = 0.0

    with caplog.at_level(logging.INFO, logger="pwm"):
        pwm.close()

    assert pwm.dc == 20.0
    assert any(
        "Stopped software PWM on GPIO-17, but unable to confirm low level" in record.message
        for record in caplog.records
    )
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


def test_cleanup_unlocks_even_if_stop_raises_pwm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    monkeypatch.setattr(pwm_module, "is_testing_env", lambda: False)
    exp = "test_cleanup_unlocks_even_if_stop_raises_pwm_error"
    unit = get_unit_name()

    pwm = PWM(17, 10, experiment=exp, unit=unit)
    pwm.lock()
    pwm.start(20)

    state["raise_when_dc"] = 0.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.clean_up()

    with local_intermittent_storage("pwm_locks") as cache:
        assert 17 not in cache


def test_cleanup_failure_is_still_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    monkeypatch.setattr(pwm_module, "is_testing_env", lambda: False)
    exp = "test_cleanup_failure_is_still_terminal"
    unit = get_unit_name()

    pwm = PWM(17, 10, experiment=exp, unit=unit)
    pwm.lock()
    pwm.start(20)

    state["raise_when_dc"] = 0.0

    with pytest.raises(PWMError, match="Failed to set software PWM"):
        pwm.clean_up()

    assert pwm._is_cleaned_up is True

    tx_calls = state["tx_calls"]
    assert isinstance(tx_calls, list)
    tx_call_count_after_failed_cleanup = len(tx_calls)

    pwm._exit("test")

    assert len(tx_calls) == tx_call_count_after_failed_cleanup


def test_exit_path_cleans_up_pwm_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    monkeypatch.setattr(pwm_module, "is_testing_env", lambda: False)
    exp = "test_exit_path_cleans_up_pwm_to_zero"
    unit = get_unit_name()

    pwm = PWM(17, 10, experiment=exp, unit=unit)
    pwm.lock()
    pwm.start(20)
    pwm._exit(signal.SIGHUP)

    tx_calls = state["tx_calls"]
    assert isinstance(tx_calls, list)
    assert tx_calls[-1] == 0.0

    with local_intermittent_storage("pwm_locks") as cache:
        assert 17 not in cache

    with local_intermittent_storage("pwm_dc") as cache:
        assert 17 not in cache


def test_cleanup_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _install_fake_lgpio(monkeypatch)
    monkeypatch.setattr(pwm_module, "is_testing_env", lambda: False)
    exp = "test_cleanup_is_idempotent"
    unit = get_unit_name()

    pwm = PWM(17, 10, experiment=exp, unit=unit)
    pwm.lock()
    pwm.start(20)
    pwm.clean_up()
    pwm.clean_up()

    tx_calls = state["tx_calls"]
    assert isinstance(tx_calls, list)
    assert tx_calls[-1] == 0.0


def test_lock_is_exclusive_after_creation() -> None:
    exp = "test_lock_is_exclusive_after_creation"
    unit = get_unit_name()

    pwm_first = PWM(12, 10, experiment=exp, unit=unit)
    pwm_second = PWM(12, 10, experiment=exp, unit=unit)

    pwm_first.lock()
    with pytest.raises(PWMError, match="GPIO-12 is currently locked"):
        pwm_second.lock()

    pwm_first.clean_up()
    pwm_second.clean_up()
