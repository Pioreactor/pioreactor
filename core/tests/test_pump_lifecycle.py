# -*- coding: utf-8 -*-
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from threading import current_thread
from threading import Event
from threading import main_thread
from threading import Thread
from unittest.mock import MagicMock

import pytest
from pioreactor.actions import pump as pumps
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.exc import PWMError
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.pwm import PWM
from tests.utils import FakeMQTTClient


def test_queued_dose_cannot_start_after_context_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    release = Event()
    entered = Event()
    starts: list[float] = []

    def occupy_worker() -> None:
        entered.set()
        assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(pumps, "_pump_thread_pool", executor)
        blocker = executor.submit(occupy_worker)
        assert entered.wait(2)
        pump = pumps.PWMPump(
            "probe",
            "probe",
            12,
            pumps.get_default_calibration(),
            mqtt_client=FakeMQTTClient(),
            logger=MagicMock(),
        )
        monkeypatch.setattr(pump.pwm._pwm, "start", starts.append)
        try:
            with pump:
                future = pump.by_duration(0.01, block=False)
        finally:
            release.set()
        blocker.result(timeout=2)
        if not future.cancelled():
            future.result(timeout=2)
        assert starts == []
        assert not pump.pwm.is_locked()


def test_closed_pwm_rejects_start() -> None:
    pwm = PWM(12, 100, unit="probe", experiment="probe", pub_client=FakeMQTTClient(), logger=MagicMock())
    pwm.clean_up()
    with pytest.raises(PWMError, match="closed|cleaned"):
        pwm.start(100)


def test_dead_pump_owner_is_recovered() -> None:
    process = subprocess.Popen(["/usr/bin/true"])
    process.wait(timeout=2)
    with local_intermittent_storage("pwm_locks") as cache:
        cache[12] = f"{process.pid}:12345"
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
    ) as pump:
        assert pump.pwm.is_locked()
        with local_intermittent_storage("pwm_locks") as cache:
            assert cache[12] == pump.pwm._lock_id


def test_busy_pump_is_an_error_not_zero_volume() -> None:
    from msgspec.structs import replace

    calibration = replace(pumps.get_default_calibration(), calibration_name="probe")
    pin = pumps._get_pin("waste_pump")
    with pumps.PWMPump("probe", "probe", pin, calibration, mqtt_client=FakeMQTTClient(), logger=MagicMock()):
        with pytest.raises(PWMError, match="locked|in use"):
            pumps.remove_waste(
                unit="probe",
                experiment="probe",
                ml=1,
                calibration=calibration,
                mqtt_client=FakeMQTTClient(),
                logger=MagicMock(),
            )


@pytest.mark.parametrize("mode", ["event", "periodic", "standalone"])
@pytest.mark.parametrize("stop", ["SIGINT", "SIGTERM", "mqtt"])
def test_shutdown_drains_pump_context(mode: str, stop: str, tmp_path: Path) -> None:
    helper = Path(__file__).with_name("pump_shutdown_probe.py")
    result = subprocess.run(
        [sys.executable, str(helper), mode, str(tmp_path), stop],
        env=os.environ | {"TESTING": "1", "SKIP_PLUGINS": "1", "PYTHONPATH": str(helper.parent.parent)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEANUP_DONE" in result.stdout, result.stdout
    with temporary_config_change(config, "storage", "temporary_cache", str(tmp_path / "temporary.sqlite")):
        with local_intermittent_storage("pwm_locks") as cache:
            assert list(cache) == [], result.stdout


def test_cancelled_owner_cannot_start_a_pump(monkeypatch: pytest.MonkeyPatch) -> None:
    cancel = Event()
    cancel.set()
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
        cancel_events=(cancel,),
    ) as pump:
        start = MagicMock()
        monkeypatch.setattr(pump.pwm._pwm, "start", start)
        pump.by_duration(10, block=True)
        assert not start.called
        assert pump.run.elapsed == 0


def test_blocked_telemetry_cannot_extend_a_dose(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = Event()
    release = Event()
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
    ) as pump:

        def block_telemetry() -> None:
            entered.set()
            assert release.wait(3)

        monkeypatch.setattr(pump.pwm, "_serialize", block_telemetry)
        reporter = Thread(target=pump.publish_duty_cycles)
        try:
            future = pump.by_duration(0.1, block=False)
            assert pump.run.started.wait(1)
            reporter.start()
            assert entered.wait(1)
            future.result(timeout=1)
            assert pump.pwm.duty_cycle == 0
            assert pump.run.completed
        finally:
            release.set()
            if reporter.ident is not None:
                reporter.join(timeout=1)


def test_busy_constructor_does_not_change_owner_state() -> None:
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
    ) as owner:
        owner.continuously(block=False)
        with pytest.raises(PWMError):
            pumps.PWMPump(
                "probe",
                "probe",
                12,
                pumps.get_default_calibration(),
                mqtt_client=FakeMQTTClient(),
                logger=MagicMock(),
            )
        with local_intermittent_storage("pwm_dc") as cache:
            assert cache[12] == 100
        with local_intermittent_storage("pwm_locks") as cache:
            assert cache[12] == owner.pwm._lock_id


def test_pause_cancel_interrupts_without_mqtt_delivery() -> None:
    cancel = Event()
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
        cancel_events=(cancel,),
    ) as pump:
        future = pump.by_duration(30, block=False)
        assert pump.run.started.wait(1)
        cancel.set()
        future.result(timeout=1)
        assert not pump.run.completed
        assert pump.pwm.duty_cycle == 0


def test_busy_telemetry_database_does_not_delay_hardware_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.utils import pwm as pwm_module

    entered, release = Event(), Event()
    original_storage = pwm_module.local_intermittent_storage
    with pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
    ) as pump:

        @contextmanager
        def slow_storage(name: str):
            if name == "pwm_dc" and current_thread() is not main_thread():
                entered.set()
                assert release.wait(3)
            with original_storage(name) as cache:
                yield cache

        monkeypatch.setattr(pwm_module, "local_intermittent_storage", slow_storage)
        reporter = Thread(target=pump.publish_duty_cycles)
        try:
            future = pump.by_duration(0.1, block=False)
            assert pump.run.started.wait(1)
            reporter.start()
            assert entered.wait(1)
            future.result(timeout=1)
            assert pump.pwm.duty_cycle == 0
        finally:
            release.set()
            if reporter.ident is not None:
                reporter.join(timeout=1)


def test_close_failure_keeps_pin_owned(monkeypatch: pytest.MonkeyPatch) -> None:
    pump = pumps.PWMPump(
        "probe",
        "probe",
        12,
        pumps.get_default_calibration(),
        mqtt_client=FakeMQTTClient(),
        logger=MagicMock(),
    )
    monkeypatch.setattr(pump.pwm._pwm, "close", MagicMock(side_effect=OSError("cannot close hardware")))
    with pytest.raises(OSError, match="cannot close hardware"):
        pump.clean_up()
    with local_intermittent_storage("pwm_locks") as cache:
        assert cache[12] == pump.pwm._lock_id


@pytest.mark.parametrize("owner", [1, "unknown", "0:123", "1:123"])
def test_unprovably_dead_lock_is_not_reclaimed(owner: object) -> None:
    with local_intermittent_storage("pwm_locks") as cache:
        cache[12] = owner
    with pytest.raises(PWMError):
        pumps.PWMPump(
            "probe",
            "probe",
            12,
            pumps.get_default_calibration(),
            mqtt_client=FakeMQTTClient(),
            logger=MagicMock(),
        )
    with local_intermittent_storage("pwm_locks") as cache:
        assert cache[12] == owner


def test_accounting_applies_intercept_once_and_excludes_queue_time() -> None:
    from msgspec.structs import replace
    from pioreactor import structs
    from pioreactor.actions.pump import estimated_volume

    calibration = replace(
        pumps.get_default_calibration(), curve_data_=structs.PolyFitCoefficients(coefficients=[2.0, 0.1])
    )
    assert estimated_volume(calibration, 0, completed=False, requested_ml=5) == 0
    assert estimated_volume(calibration, 0.5, completed=False, requested_ml=5) == pytest.approx(1.1)
    assert estimated_volume(calibration, 1.0, completed=False, requested_ml=5) == pytest.approx(2.1)
    assert estimated_volume(calibration, 0.001, completed=True, requested_ml=0.001) == 0.001
    assert estimated_volume(calibration, 10, completed=False, requested_ml=5) == 5
    assert estimated_volume(calibration, 0, completed=True, requested_ml=5) == 0
    assert estimated_volume(calibration, 1, completed=True, requested_ml=-0.1) == 0
    assert estimated_volume(calibration, 0.5, completed=False, requested_ml=-0.1) == 0


@pytest.mark.parametrize("mode", ["blocking", "continuous", "nonblocking"])
def test_cancel_while_waiting_for_a_control_worker(monkeypatch: pytest.MonkeyPatch, mode: str) -> None:
    from threading import Thread
    from tests.utils import wait_for

    release, occupied, cancel = Event(), Event(), Event()
    errors: list[Exception] = []

    def occupy() -> None:
        occupied.set()
        assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(pumps, "_pump_thread_pool", executor)
        blocker = executor.submit(occupy)
        assert occupied.wait(1)
        with pumps.PWMPump(
            "probe",
            "probe",
            12,
            pumps.get_default_calibration(),
            mqtt_client=FakeMQTTClient(),
            logger=MagicMock(),
            cancel_events=(cancel,),
        ) as pump:

            def call() -> None:
                try:
                    if mode == "continuous":
                        pump.continuously(block=False)
                    elif mode == "blocking":
                        pump.by_duration(10, block=True)
                    else:
                        pump.by_duration(10, block=False)
                        while not pump.wait(0.05):
                            pass
                        pump.stop()
                except Exception as error:
                    errors.append(error)

            caller = Thread(target=call)
            caller.start()
            try:
                assert wait_for(lambda: pump.run is not None, timeout=1)
                cancel.set()
                caller.join(timeout=1)
                assert not caller.is_alive()
                assert errors == []
                assert pump.run.started_at is None
            finally:
                release.set()
                caller.join(timeout=2)
        blocker.result(timeout=2)


def test_only_one_contender_can_recover_a_dead_owner() -> None:
    from threading import Barrier
    from tests.utils import wait_for

    process = subprocess.Popen(["/usr/bin/true"])
    process.wait(timeout=2)
    with local_intermittent_storage("pwm_locks") as cache:
        cache[12] = f"{process.pid}:12345"
    barrier = Barrier(3)
    release = Event()
    outcomes: list[str] = []

    def contend() -> None:
        barrier.wait(timeout=2)
        try:
            with pumps.PWMPump(
                "probe",
                "probe",
                12,
                pumps.get_default_calibration(),
                mqtt_client=FakeMQTTClient(),
                logger=MagicMock(),
            ):
                outcomes.append("acquired")
                assert release.wait(3)
        except PWMError:
            outcomes.append("locked")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(contend) for _ in range(2)]
        barrier.wait(timeout=2)
        try:
            assert wait_for(lambda: len(outcomes) == 2, timeout=2)
            assert sorted(outcomes) == ["acquired", "locked"]
        finally:
            release.set()
        for future in futures:
            future.result(timeout=2)


def test_circulation_cancellation_interrupts_the_active_media_pulse(monkeypatch: pytest.MonkeyPatch) -> None:
    from threading import Thread
    from msgspec.structs import replace
    from pioreactor import structs
    from tests.utils import wait_for

    cancel = Event()
    client = FakeMQTTClient()
    calibration = replace(
        pumps.get_default_calibration(),
        calibration_name="probe",
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
    )
    created: list[pumps.PWMPump] = []
    result: list[tuple[float, float]] = []
    errors: list[Exception] = []
    original_pump = pumps.PWMPump

    class Lifecycle:
        mqtt_client = client
        exit_event = cancel

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            pass

    def construct(*args, **kwargs) -> pumps.PWMPump:
        instance = original_pump(*args, **kwargs)
        created.append(instance)
        return instance

    monkeypatch.setattr(pumps, "PWMPump", construct)
    monkeypatch.setattr(pumps, "_get_calibration", lambda device: calibration)
    monkeypatch.setattr(pumps.utils, "managed_lifecycle", lambda *args, **kwargs: Lifecycle())

    def circulate() -> None:
        try:
            result.append(pumps.circulate_media(30, unit="probe", experiment="probe", logger=MagicMock()))
        except Exception as error:
            errors.append(error)

    caller = Thread(target=circulate)
    caller.start()
    try:
        assert wait_for(
            lambda: len(created) == 2
            and created[1].run is not None
            and created[1].run.started_at is not None,
            timeout=3,
        )
        cancel.set()
        caller.join(timeout=1)
        assert not caller.is_alive()
        assert errors == []
        media, waste = result[0]
        assert 0 < media < 0.85
        assert waste >= 1
        assert all(not pump.pwm.is_locked() for pump in created)
    finally:
        cancel.set()
        caller.join(timeout=2)


def test_continuous_inflow_is_bounded_even_without_volume_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    from msgspec.structs import replace
    from pioreactor import structs
    from pioreactor.whoami import get_pioreactor_model

    calibration = replace(
        pumps.get_default_calibration(),
        calibration_name="probe",
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
    )
    maximum = get_pioreactor_model().reactor_max_fill_volume_ml
    monkeypatch.setattr(pumps.bioreactor, "get_bioreactor_value", lambda *args: maximum - 0.1)
    client = FakeMQTTClient()
    moved = pumps.add_media(
        unit="probe",
        experiment="probe",
        continuously=True,
        calibration=calibration,
        mqtt_client=client,
        logger=MagicMock(),
    )
    assert 0.09 <= moved < 0.2
    with local_intermittent_storage("pwm_locks") as cache:
        assert pumps._get_pin("media_pump") not in cache
    assert all(
        call["kwargs"]["qos"] == 2
        for call in client.publish_calls
        if call["topic"].endswith("/dosing_events")
    )
