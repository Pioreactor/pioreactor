# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
from datetime import datetime
from datetime import timezone

import pytest
from msgspec.json import encode

from pioreactor import structs
from pioreactor.actions.pump import add_alt_media
from pioreactor.actions.pump import add_media
from pioreactor.actions.pump import circulate_media
from pioreactor.actions.pump import PWMPump
from pioreactor.actions.pump import remove_waste
from pioreactor.exc import CalibrationError
from pioreactor.exc import PWMError
from pioreactor.pubsub import create_client
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import timing
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1):
    time.sleep(n)


def setup_function():
    with local_persistant_storage("current_pump_calibration") as cache:
        cache["media"] = encode(
            structs.MediaPumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0.0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="media",
                pioreactor_unit=unit,
            )
        )
        cache["alt_media"] = encode(
            structs.AltMediaPumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="alt_media",
                pioreactor_unit=unit,
            )
        )
        cache["waste"] = encode(
            structs.WastePumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="waste",
                pioreactor_unit=unit,
            )
        )


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


def test_pump_fails_if_calibration_not_present() -> None:
    exp = "test_pump_fails_if_calibration_not_present"

    with local_persistant_storage("current_pump_calibration") as cache:
        del cache["media"]
        del cache["alt_media"]
        del cache["waste"]

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
        def __init__(self, *init_args, **init_kwargs):
            threading.Thread.__init__(self, *init_args, **init_kwargs)
            self._return = None

        def run(self):
            self._return = self._target(*self._args, **self._kwargs)

        def join(self):
            threading.Thread.join(self)
            return self._return

    expected_ml = 20
    t = ThreadWithReturnValue(target=add_media, args=(unit, exp, expected_ml), daemon=True)
    t.start()

    pause()
    pause()
    publish(f"pioreactor/{unit}/{exp}/add_media/$state/set", b"disconnected", qos=1)
    pause()
    pause()

    pause()

    resulting_ml = t.join()

    assert resulting_ml < expected_ml


def test_continuously_running_pump_will_disconnect_via_mqtt() -> None:
    exp = "test_continuously_running_pump_will_disconnect_via_mqtt"

    class ThreadWithReturnValue(threading.Thread):
        def __init__(self, *init_args, **init_kwargs):
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
        publish(f"pioreactor/{unit}/{exp}/add_media/$state/set", b"disconnected", qos=1)
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
    calibration = structs.MediaPumpCalibration(
        name="setup_function",
        duration_=1.0,
        bias_=0.0,
        dc=100,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        pump="media",
        pioreactor_unit=unit,
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


def test_pumps_can_run_in_background() -> None:
    experiment = "test_pumps_can_run_in_background"

    calibration = structs.MediaPumpCalibration(
        name="setup_function",
        duration_=1.0,
        bias_=0.0,
        dc=60,
        hz=100,
        created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
        voltage=-1.0,
        pump="media",
        pioreactor_unit=unit,
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

    with pytest.raises(PWMError):
        remove_waste(unit, exp, duration=5.0)

    t.join()


def test_media_circulation_will_control_media_pump_if_it_has_a_higher_flow_rate() -> None:
    exp = "test_media_circulation_will_control_media_pump_if_it_has_a_higher_rate"

    with local_persistant_storage("current_pump_calibration") as cache:
        cache["media"] = encode(
            structs.MediaPumpCalibration(
                name="setup_function",
                duration_=10.0,
                bias_=0.0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="media",
                pioreactor_unit=unit,
            )
        )
        cache["waste"] = encode(
            structs.WastePumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="waste",
                pioreactor_unit=unit,
            )
        )

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert (waste_removed - 2) >= media_added


def test_media_circulation_will_control_media_pump_if_it_has_a_lower_flow_rate() -> None:
    exp = "test_media_circulation_will_control_media_pump_if_it_has_a_lower_flow_rate"

    with local_persistant_storage("current_pump_calibration") as cache:
        cache["media"] = encode(
            structs.MediaPumpCalibration(
                name="setup_function",
                duration_=0.15,
                bias_=0.0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="media",
                pioreactor_unit=unit,
            )
        )
        cache["waste"] = encode(
            structs.WastePumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                created_at=datetime(2010, 1, 1, tzinfo=timezone.utc),
                voltage=-1.0,
                pump="waste",
                pioreactor_unit=unit,
            )
        )

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert (waste_removed - 2) >= media_added


def test_media_circulation_works_without_calibration_since_we_are_entering_duration() -> None:
    exp = "test_media_circulation_works_without_calibration_since_we_are_entering_duration"
    with local_persistant_storage("current_pump_calibration") as cache:
        del cache["media"]
        del cache["waste"]

    media_added, waste_removed = circulate_media(5.0, unit, exp)
    assert waste_removed >= media_added


def test_manually_doesnt_trigger_pwm_dcs() -> None:
    ml = 1.0
    exp = "test_manually_doesnt_trigger_pwm_dcs"

    pwm_updates = []

    def collect_pwm_updates(msg):
        pwm_updates.append(msg.payload.decode())

    subscribe_and_callback(collect_pwm_updates, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)
    assert add_media(ml=ml, unit=unit, experiment=exp, manually=True) == 0.0
    assert add_alt_media(ml=ml, unit=unit, experiment=exp, manually=True) == 0.0
    assert remove_waste(ml=ml, unit=unit, experiment=exp, manually=True) == 0.0

    assert len(pwm_updates) == 3
    assert pwm_updates[0] == r"{}"
    assert pwm_updates[1] == r"{}"
    assert pwm_updates[2] == r"{}"


def test_can_provide_mqtt_client() -> None:
    experiment = "test_can_provide_mqtt_client"
    client = create_client(hostname="localhost")
    time.sleep(4)
    add_media(ml=1.0, unit=unit, experiment=experiment, mqtt_client=client)
    info = client.publish(topic="test_can_provide_mqtt_client", payload="hello!")
    info.wait_for_publish()
