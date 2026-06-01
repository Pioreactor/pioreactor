# -*- coding: utf-8 -*-
import json
import threading
import time
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import cast

import pytest
from pioreactor import bioreactor
from pioreactor import structs
from pioreactor.actions.pump import _get_pin
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import circulate_media
from pioreactor.actions.pump import publish_async
from pioreactor.actions.pump import PWMPump
from pioreactor.actions.pump import remove_waste
from pioreactor.background_jobs.monitor import Monitor
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.exc import CalibrationError
from pioreactor.exc import PWMError
from pioreactor.pubsub import create_client
from pioreactor.pubsub import publish
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistent_storage
from pioreactor.utils import timing
from pioreactor.whoami import get_unit_name
from tests.utils import FakeMQTTClient

unit = get_unit_name()


def _poly_curve(coefficients: list[float]) -> structs.PolyFitCoefficients:
    return structs.PolyFitCoefficients(coefficients=coefficients)


def pause(n=1):
    time.sleep(n)


class _RunInlineThreadPool:
    def submit(self, fn, *args, **kwargs) -> None:
        fn(*args, **kwargs)


class _SequenceInterrupt:
    def __init__(self, is_set_results: list[bool]) -> None:
        self._is_set_results = is_set_results
        self._is_set = False

    def is_set(self) -> bool:
        if self._is_set_results:
            return self._is_set_results.pop(0)
        return self._is_set

    def set(self) -> None:
        self._is_set = True

    def wait(self) -> bool:
        return self.is_set()


class _SequenceExitEvent:
    def __init__(self, wait_results: list[bool]) -> None:
        self._wait_results = wait_results

    def wait(self, timeout: float | None = None) -> bool:
        if self._wait_results:
            return self._wait_results.pop(0)
        return False


class _FakeManagedLifecycle:
    def __init__(self, mqtt_client: FakeMQTTClient, exit_wait_results: list[bool]) -> None:
        self.mqtt_client = mqtt_client
        self.exit_event = _SequenceExitEvent(exit_wait_results)

    def __enter__(self) -> "_FakeManagedLifecycle":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _linear_pump_calibration(slope: float = 1.0) -> structs.SimplePeristalticPumpCalibration:
    return structs.SimplePeristalticPumpCalibration(
        calibration_name="linear",
        curve_data_=_poly_curve([slope, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )


def _fake_client_collecting_dosing_events(experiment: str) -> tuple[FakeMQTTClient, list[float]]:
    dosing_events: list[float] = []

    def collect_dosing_events(topic: str, payload: bytes, **kwargs: Any) -> None:
        if topic == f"pioreactor/{unit}/{experiment}/dosing_events":
            dosing_events.append(json.loads(payload.decode())["volume_change"])

    return FakeMQTTClient(on_publish=collect_dosing_events), dosing_events


def _set_up_deterministic_pump_action(
    monkeypatch: pytest.MonkeyPatch,
    mqtt_client: FakeMQTTClient,
    *,
    exit_wait_results: list[bool] | None = None,
) -> None:
    monkeypatch.setattr("pioreactor.actions.pump._thread_pool", cast(Any, _RunInlineThreadPool()))
    monkeypatch.setattr(
        "pioreactor.actions.pump.utils.managed_lifecycle",
        lambda *args, **kwargs: _FakeManagedLifecycle(mqtt_client, exit_wait_results or []),
    )


def _build_scheduled_pump_type(
    interrupt_results: list[bool],
    pump_actuations: list[tuple[float, bool]],
    pump_exits: list[bool],
) -> type:
    class ScheduledPump:
        def __init__(self, *args, **kwargs) -> None:
            self.interrupt = _SequenceInterrupt(interrupt_results.copy())
            self.calibration = kwargs["calibration"]

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pump_exits.append(True)

        def by_duration(self, seconds: float, block: bool = True) -> None:
            pump_actuations.append((seconds, block))

        def continuously(self, block: bool = True) -> None:
            raise AssertionError("continuous path is not under test")

        def duration_to_ml(self, seconds: float) -> float:
            return self.calibration.duration_to_ml(seconds)

        def stop(self) -> None:
            self.interrupt.set()

    return ScheduledPump


@pytest.fixture(autouse=True)
def use_expected_alt_media_pwm_channel():
    with temporary_config_change(config, "PWM_reverse", "alt_media", "4"):
        yield


def setup_function():
    cal = structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )
    cal.set_as_active_calibration_for_device("media_pump")
    cal.set_as_active_calibration_for_device("alt_media_pump")
    cal.set_as_active_calibration_for_device("waste_pump")

    cal.save_to_disk_for_device("media_pump")
    cal.save_to_disk_for_device("alt_media_pump")
    cal.save_to_disk_for_device("waste_pump")


def test_pump_io() -> None:
    exp = "test_pump_io"
    ml = 0.1
    assert ml == add_media(ml=ml, unit=unit, experiment=exp)
    assert ml == add_alt_media(ml=ml, unit=unit, experiment=exp)
    assert ml == remove_waste(ml=ml, unit=unit, experiment=exp)

    ml = 1.0
    assert ml == add_media(duration=ml, unit=unit, experiment=exp)
    assert ml == add_alt_media(duration=ml, unit=unit, experiment=exp)
    assert ml == remove_waste(duration=ml, unit=unit, experiment=exp)


def test_publish_async_uses_exactly_once_when_requested(monkeypatch) -> None:
    publish_calls: list[tuple[str, bytes, dict[str, int]]] = []

    class FakeThreadPool:
        def submit(self, fn, *args, **kwargs) -> None:
            fn(*args, **kwargs)

    monkeypatch.setattr("pioreactor.actions.pump._thread_pool", cast(Any, FakeThreadPool()))
    client = FakeMQTTClient(
        on_publish=lambda topic, payload, **kwargs: publish_calls.append((topic, payload, kwargs))
    )
    publish_async(cast(Any, client), "pioreactor/unit/exp/dosing_events", b"{}", qos=QOS.EXACTLY_ONCE)
    assert publish_calls == [("pioreactor/unit/exp/dosing_events", b"{}", {"qos": QOS.EXACTLY_ONCE})]


@pytest.mark.skip(reason="...")
def test_public_add_media_updates_bioreactor_state() -> None:
    exp = "test_public_add_media_updates_bioreactor_state"

    with Monitor(unit=unit, experiment="$experiment"):
        assert bioreactor.get_bioreactor_value(exp, "current_volume_ml") == pytest.approx(14.0)

        moved_ml = add_media(ml=1.25, unit=unit, experiment=exp)
        pause(2)

    assert moved_ml == pytest.approx(1.25)
    assert bioreactor.get_bioreactor_value(exp, "current_volume_ml") == pytest.approx(15.25)


@pytest.mark.skip(reason="...")
def test_public_add_alt_media_updates_bioreactor_state() -> None:
    exp = "test_public_add_alt_media_updates_bioreactor_state"

    with Monitor(unit=unit, experiment="$experiment"):
        moved_ml = add_alt_media(ml=1.0, unit=unit, experiment=exp)
        pause(2)

    assert moved_ml == pytest.approx(1.0)
    assert bioreactor.get_bioreactor_value(exp, "current_volume_ml") == pytest.approx(15.0)
    assert bioreactor.get_bioreactor_value(exp, "alt_media_fraction") == pytest.approx(1 / 15)


def test_pump_fails_if_calibration_not_present() -> None:
    exp = "test_pump_fails_if_calibration_not_present"

    with local_persistent_storage("active_calibrations") as c:
        c.pop("media_pump")
        c.pop("alt_media_pump")
        c.pop("waste_pump")

    with pytest.raises(CalibrationError):
        add_media(ml=1.0, unit=unit, experiment=exp)

    with pytest.raises(CalibrationError):
        add_alt_media(ml=1.0, unit=unit, experiment=exp)

    with pytest.raises(CalibrationError):
        remove_waste(ml=1.0, unit=unit, experiment=exp)


def test_pump_io_doesnt_allow_negative() -> None:
    exp = "test_pump_io_doesnt_allow_negative"
    with pytest.raises(ValueError):
        add_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        add_alt_media(ml=-1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        remove_waste(ml=-1, unit=unit, experiment=exp)

    with pytest.raises(ValueError):
        add_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        add_alt_media(duration=-1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        remove_waste(duration=-1, unit=unit, experiment=exp)


def test_negative_duration_is_rejected_before_constructing_pump(monkeypatch) -> None:
    exp = "test_negative_duration_is_rejected_before_constructing_pump"

    class FailIfConstructed:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("PWMPump should not be constructed for negative durations")

    monkeypatch.setattr("pioreactor.actions.pump.PWMPump", FailIfConstructed)

    with pytest.raises(ValueError):
        add_media(duration=-1, unit=unit, experiment=exp)


def test_pump_io_cant_set_both_duration_and_ml() -> None:
    exp = "test_pump_io_cant_set_both_duration_and_ml"
    with pytest.raises(ValueError):
        add_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        add_alt_media(ml=1, duration=1, unit=unit, experiment=exp)
    with pytest.raises(ValueError):
        remove_waste(ml=1, duration=1, unit=unit, experiment=exp)


def test_pump_will_disconnect_via_mqtt() -> None:
    exp = "test_pump_will_disconnect_via_mqtt"

    class ThreadWithReturnValue(threading.Thread):
        def __init__(self, *init_args, **init_kwargs) -> None:
            threading.Thread.__init__(self, *init_args, **init_kwargs)
            self._return = None

        def run(self):
            self._return = self._target(*self._args, **self._kwargs)

        def join(self):
            threading.Thread.join(self)
            return self._return

    volume_updates = []

    def collect_updates(msg):
        volume_updates.append(json.loads(msg.payload.decode()))

    subscribe_and_callback(collect_updates, f"pioreactor/{unit}/{exp}/dosing_events", allow_retained=False)

    expected_ml = 10
    t = ThreadWithReturnValue(target=add_media, args=(unit, exp, expected_ml), daemon=True)
    t.start()

    pause()
    pause()
    time.sleep(0.1)
    publish(
        f"pioreactor/{unit}/{exp}/add_media/$state/set",
        b"disconnected",
        qos=QOS.AT_LEAST_ONCE,
    )
    pause()
    pause()

    pause()

    resulting_ml = t.join()

    assert resulting_ml < expected_ml

    assert volume_updates[0]["volume_change"] > 0
    assert -expected_ml < volume_updates[-1]["volume_change"] < 0  # fire off a negative volume change


def test_continuously_running_pump_will_disconnect_via_mqtt() -> None:
    exp = "test_continuously_running_pump_will_disconnect_via_mqtt"

    class ThreadWithReturnValue(threading.Thread):
        def __init__(self, *init_args, **init_kwargs) -> None:
            threading.Thread.__init__(self, *init_args, **init_kwargs)
            self._return = None

        def run(self):
            self._return = self._target(*self._args, **self._kwargs)

        def join(self):
            threading.Thread.join(self)
            return self._return

    t = ThreadWithReturnValue(target=add_media, args=(unit, exp), kwargs={"continuously": True}, daemon=True)
    t.start()

    pause()
    pause()
    with timing.catchtime() as elapsed_time:
        publish(
            f"pioreactor/{unit}/{exp}/add_media/$state/set",
            b"disconnected",
            qos=QOS.AT_LEAST_ONCE,
        )
        assert elapsed_time() < 1.5

    resulting_ml = t.join()
    assert resulting_ml > 0


def test_pump_publishes_to_state() -> None:
    exp = "test_pump_publishes_to_state"

    add_media(ml=1, unit=unit, experiment=exp)
    r = subscribe(f"pioreactor/{unit}/{exp}/add_media/$state", timeout=3)
    if r is not None:
        assert r.payload.decode() == "disconnected"
    else:
        assert False


def test_pump_can_be_interrupted() -> None:
    experiment = "test_pump_can_be_interrupted"
    calibration = structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=100,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )

    with PWMPump(unit=unit, experiment=experiment, pin=13, calibration=calibration) as p:
        p.continuously(block=False)
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache[13] == 100

        p.stop()
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 0

        p.by_duration(seconds=100, block=False)
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache[13] == 100

        p.stop()
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 0

        p.by_volume(ml=100, block=False)
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache[13] == 100

        p.stop()
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 0


def test_pump_stop_is_safe_after_pwm_cleanup() -> None:
    experiment = "test_pump_stop_is_safe_after_pwm_cleanup"
    calibration = structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=100,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )

    pump = PWMPump(unit=unit, experiment=experiment, pin=13, calibration=calibration)
    pump.continuously(block=False)
    pause()

    pump.clean_up()
    pump.stop()

    with local_intermittent_storage("pwm_dc") as cache:
        assert cache.get(13, 0) == 0


def test_add_media_publishes_single_empty_pwm_payload_on_shutdown() -> None:
    experiment = "test_add_media_publishes_single_empty_pwm_payload_on_shutdown"

    mqtt_items: list[dict[str, float]] = []

    def collect(msg) -> None:
        payload = msg.payload.decode()
        if not payload:
            return
        mqtt_items.append(json.loads(payload))

    subscribe_and_callback(collect, f"pioreactor/{unit}/{experiment}/pwms/dc", allow_retained=False)

    moved_ml = add_media(ml=1.0, unit=unit, experiment=experiment)
    pause()

    assert moved_ml == pytest.approx(1.0)
    assert mqtt_items[-1] == {}
    assert sum(payload == {} for payload in mqtt_items) == 1


def test_small_volume_reports_requested_amount_if_pump_finishes_immediately(monkeypatch) -> None:
    experiment = "test_small_volume_reports_requested_amount_if_pump_finishes_immediately"
    requested_ml = 0.01
    dosing_events: list[float] = []
    pump_actuations: list[tuple[float, bool]] = []
    pump_exited = False

    calibration = structs.SimplePeristalticPumpCalibration(
        calibration_name="fast_finish",
        curve_data_=_poly_curve([20.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )

    class FastCompletingPump:
        def __init__(self, *args, **kwargs) -> None:
            self.interrupt = threading.Event()
            self.calibration = kwargs["calibration"]

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            nonlocal pump_exited
            pump_exited = True

        def by_duration(self, seconds: float, block: bool = True) -> None:
            pump_actuations.append((seconds, block))
            self.interrupt.set()

        def continuously(self, block: bool = True) -> None:
            raise AssertionError("continuous path is not under test")

        def duration_to_ml(self, seconds: float) -> float:
            return self.calibration.duration_to_ml(seconds)

        def stop(self) -> None:
            self.interrupt.set()

    class FakeThreadPool:
        def submit(self, fn, *args, **kwargs) -> None:
            fn(*args, **kwargs)

    def collect_dosing_events(topic: str, payload: bytes, **kwargs: Any) -> None:
        if topic == f"pioreactor/{unit}/{experiment}/dosing_events":
            dosing_events.append(json.loads(payload.decode())["volume_change"])

    client = FakeMQTTClient(on_publish=collect_dosing_events)
    monkeypatch.setattr("pioreactor.actions.pump._thread_pool", cast(Any, FakeThreadPool()))
    monkeypatch.setattr("pioreactor.actions.pump.PWMPump", FastCompletingPump)

    moved_ml = add_media(
        ml=requested_ml,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    assert len(pump_actuations) == 1
    assert pump_actuations[0][0] == pytest.approx(calibration.ml_to_duration(requested_ml))
    assert pump_actuations[0][1] is False
    assert pump_exited
    assert moved_ml == pytest.approx(requested_ml)
    assert dosing_events == [pytest.approx(requested_ml)]
    assert sum(dosing_events) == pytest.approx(moved_ml)


def test_finite_pump_reconciles_completion_between_accounting_ticks(monkeypatch) -> None:
    experiment = "test_finite_pump_reconciles_completion_between_accounting_ticks"
    requested_ml = 0.8
    pump_actuations: list[tuple[float, bool]] = []
    pump_exits: list[bool] = []
    calibration = _linear_pump_calibration()
    client, dosing_events = _fake_client_collecting_dosing_events(experiment)

    _set_up_deterministic_pump_action(monkeypatch, client, exit_wait_results=[False])
    monkeypatch.setattr(
        "pioreactor.actions.pump.PWMPump",
        _build_scheduled_pump_type([False, True], pump_actuations, pump_exits),
    )
    monkeypatch.setattr("pioreactor.actions.pump.time.monotonic", iter([0.0, 0.0]).__next__)

    moved_ml = add_media(
        ml=requested_ml,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    assert pump_actuations == [(requested_ml, False)]
    assert pump_exits == [True]
    assert dosing_events == pytest.approx([0.5, 0.3])
    assert sum(dosing_events) == pytest.approx(moved_ml)
    assert moved_ml == pytest.approx(requested_ml)


def test_finite_pump_does_not_publish_terminal_event_at_exact_accounting_boundary(monkeypatch) -> None:
    experiment = "test_finite_pump_does_not_publish_terminal_event_at_exact_accounting_boundary"
    requested_ml = 1.0
    pump_actuations: list[tuple[float, bool]] = []
    pump_exits: list[bool] = []
    calibration = _linear_pump_calibration()
    client, dosing_events = _fake_client_collecting_dosing_events(experiment)

    _set_up_deterministic_pump_action(monkeypatch, client, exit_wait_results=[False, False])
    monkeypatch.setattr(
        "pioreactor.actions.pump.PWMPump",
        _build_scheduled_pump_type([False, False, True], pump_actuations, pump_exits),
    )
    monkeypatch.setattr("pioreactor.actions.pump.time.monotonic", iter([0.0, 0.0, 0.5]).__next__)

    moved_ml = add_media(
        ml=requested_ml,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    assert pump_actuations == [(requested_ml, False)]
    assert pump_exits == [True]
    assert dosing_events == pytest.approx([0.5, 0.5])
    assert sum(dosing_events) == pytest.approx(moved_ml)
    assert moved_ml == pytest.approx(requested_ml)


def test_interrupted_finite_pump_published_total_matches_returned_volume(monkeypatch) -> None:
    experiment = "test_interrupted_finite_pump_published_total_matches_returned_volume"
    requested_ml = 1.0
    pump_actuations: list[tuple[float, bool]] = []
    pump_exits: list[bool] = []
    calibration = _linear_pump_calibration()
    client, dosing_events = _fake_client_collecting_dosing_events(experiment)

    _set_up_deterministic_pump_action(monkeypatch, client, exit_wait_results=[True])
    monkeypatch.setattr(
        "pioreactor.actions.pump.PWMPump", _build_scheduled_pump_type([False], pump_actuations, pump_exits)
    )
    monkeypatch.setattr("pioreactor.actions.pump.time.monotonic", iter([0.0, 0.0, 0.25]).__next__)

    moved_ml = add_media(
        ml=requested_ml,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    assert pump_actuations == [(requested_ml, False)]
    assert pump_exits == [True]
    assert dosing_events == pytest.approx([0.5, -0.25])
    assert sum(dosing_events) == pytest.approx(moved_ml)
    assert moved_ml == pytest.approx(0.25)


def test_zero_volume_request_keeps_pwm_off_and_emits_no_dosing_event(monkeypatch) -> None:
    experiment = "test_zero_volume_request_keeps_pwm_off_and_emits_no_dosing_event"
    pin = _get_pin("media_pump")
    calibration = _linear_pump_calibration()
    client, dosing_events = _fake_client_collecting_dosing_events(experiment)

    _set_up_deterministic_pump_action(monkeypatch, client)

    moved_ml = add_media(
        ml=0.0,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    with local_intermittent_storage("pwm_dc") as pwm_dc:
        assert pwm_dc.get(pin, 0) == 0
    with local_intermittent_storage("pwm_locks") as pwm_locks:
        assert pin not in pwm_locks

    assert moved_ml == pytest.approx(0.0)
    assert dosing_events == []


def test_immediate_completion_cleans_up_pwm_state_and_lock(monkeypatch) -> None:
    experiment = "test_immediate_completion_cleans_up_pwm_state_and_lock"
    requested_ml = 0.01
    pin = _get_pin("media_pump")
    calibration = _linear_pump_calibration(slope=20.0)
    client, dosing_events = _fake_client_collecting_dosing_events(experiment)

    _set_up_deterministic_pump_action(monkeypatch, client)

    moved_ml = add_media(
        ml=requested_ml,
        unit=unit,
        experiment=experiment,
        calibration=calibration,
        mqtt_client=cast(Any, client),
    )

    with local_intermittent_storage("pwm_dc") as pwm_dc:
        assert pwm_dc.get(pin, 0) == 0
    with local_intermittent_storage("pwm_locks") as pwm_locks:
        assert pin not in pwm_locks

    assert moved_ml == pytest.approx(requested_ml)
    assert dosing_events == [pytest.approx(requested_ml)]


def test_pumps_can_run_in_background() -> None:
    experiment = "test_pumps_can_run_in_background"

    calibration = structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    )
    with PWMPump(unit=unit, experiment=experiment, pin=13, calibration=calibration) as p:
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 0

        p.by_volume(ml=100, block=False)
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 60

        p.stop()
        pause()
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache.get(13, 0) == 0


def test_media_circulation() -> None:
    exp = "test_media_circulation"
    media_added, waste_removed = circulate_media(5, unit, exp)
    assert waste_removed > media_added


def test_media_circulation_uses_remaining_duration_for_final_media_pulse(monkeypatch) -> None:
    exp = "test_media_circulation_uses_remaining_duration"
    media_durations: list[float] = []

    class FakeExitEvent:
        def is_set(self) -> bool:
            return False

        def wait(self, timeout: float) -> bool:
            return False

    class FakeLifecycle:
        mqtt_client = FakeMQTTClient()
        exit_event = FakeExitEvent()

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    class FakePump:
        def __init__(self, unit, experiment, pin, calibration, mqtt_client=None, logger=None) -> None:
            self.pin = pin

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def continuously(self, block: bool) -> None:
            return None

        def by_duration(self, duration: float, block: bool) -> None:
            if self.pin == 2:
                media_durations.append(duration)

        def stop(self) -> None:
            return None

    monkeypatch.setattr(
        "pioreactor.actions.pump._get_pin", lambda pump_device: 1 if pump_device == "waste_pump" else 2
    )
    monkeypatch.setattr("pioreactor.actions.pump.PWMPump", FakePump)
    monkeypatch.setattr(
        "pioreactor.actions.pump.utils.managed_lifecycle", lambda *args, **kwargs: FakeLifecycle()
    )
    monkeypatch.setattr("pioreactor.actions.pump.time.sleep", lambda seconds: None)

    media_added, _waste_removed = circulate_media(1.2, unit, exp)

    assert media_durations == pytest.approx([0.85, 0.35])
    assert media_added == pytest.approx(1.2)


def test_media_circulation_cant_run_when_waste_pump_is_running() -> None:
    from threading import Thread

    exp = "test_media_circulation_cant_run_when_waste_pump_is_running"
    t = Thread(target=remove_waste, kwargs={"duration": 3.0, "experiment": exp, "unit": unit})
    t.start()
    time.sleep(0.1)

    with pytest.raises(PWMError):
        circulate_media(5.0, unit, exp)

    t.join()


def test_waste_pump_cant_run_when_media_circulation_is_running() -> None:
    from threading import Thread

    exp = "test_waste_pump_cant_run_when_media_circulation_is_running"
    t = Thread(target=circulate_media, kwargs={"duration": 3.0, "experiment": exp, "unit": unit})
    t.start()
    time.sleep(0.1)

    assert remove_waste(unit, exp, duration=5.0) == 0

    t.join()


def test_media_circulation_will_control_media_pump_if_it_has_a_higher_flow_rate() -> None:
    exp = "test_media_circulation_will_control_media_pump_if_it_has_a_higher_rate"
    structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([10.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    ).set_as_active_calibration_for_device("media_pump")

    structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    ).set_as_active_calibration_for_device("waste_pump")

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert (waste_removed - 2) >= media_added


def test_media_circulation_will_control_media_pump_if_it_has_a_lower_flow_rate() -> None:
    exp = "test_media_circulation_will_control_media_pump_if_it_has_a_lower_flow_rate"

    structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([0.15, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    ).set_as_active_calibration_for_device("media_pump")

    structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=_poly_curve([1.0, 0.0]),
        recorded_data={"x": [], "y": []},
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        calibrated_on_pioreactor_unit=unit,
    ).set_as_active_calibration_for_device("waste_pump")

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert (waste_removed - 2) >= media_added


def test_media_circulation_works_without_calibration_since_we_are_entering_duration() -> None:
    exp = "test_media_circulation_works_without_calibration_since_we_are_entering_duration"

    with local_persistent_storage("active_calibrations") as c:
        c.pop("media_pump")
        c.pop("alt_media_pump")
        c.pop("waste_pump")

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert waste_removed >= media_added


@pytest.mark.slow
def test_published_mqtt_data_is_the_same_as_requested() -> None:
    exp = "test_published_mqtt_data_is_the_same_as_requested"

    dosing_events = []

    def collect_dosing_events(msg):
        dosing_events.append(json.loads(msg.payload.decode())["volume_change"])

    subscribe_and_callback(
        collect_dosing_events, f"pioreactor/{unit}/{exp}/dosing_events", allow_retained=False
    )

    vol = 5.12314
    assert add_media(unit=unit, experiment=exp, ml=vol) == vol
    assert sum(dosing_events) == vol

    # try remove waste too
    dosing_events = []

    vol = 5.12314
    assert remove_waste(unit=unit, experiment=exp, ml=vol) == vol
    assert sum(dosing_events) == vol


def test_can_provide_mqtt_client() -> None:
    experiment = "test_can_provide_mqtt_client"
    client = create_client(hostname="localhost")
    time.sleep(4)
    add_media(ml=1.0, unit=unit, experiment=experiment, mqtt_client=client)
    info = client.publish(topic="test_can_provide_mqtt_client", payload="hello!")
    info.wait_for_publish()
