# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from datetime import datetime
from datetime import timedelta
from typing import Any

import pytest
from msgspec.json import encode

from pioreactor import exc
from pioreactor import pubsub
from pioreactor import structs
from pioreactor.automations import DosingAutomationJob
from pioreactor.automations import events
from pioreactor.automations.dosing.base import AltMediaCalculator
from pioreactor.automations.dosing.continuous_cycle import ContinuousCycle
from pioreactor.automations.dosing.morbidostat import Morbidostat
from pioreactor.automations.dosing.pid_morbidostat import PIDMorbidostat
from pioreactor.automations.dosing.silent import Silent
from pioreactor.automations.dosing.turbidostat import Turbidostat
from pioreactor.background_jobs.dosing_control import DosingController
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.timing import current_utc_timestamp
from pioreactor.whoami import get_unit_name


unit = get_unit_name()


def pause() -> None:
    # to avoid race conditions when updating state
    time.sleep(0.5)


def setup_function() -> None:
    with local_persistant_storage("current_pump_calibration") as cache:
        cache["media"] = encode(
            structs.MediaPumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0.0,
                dc=60,
                hz=100,
                timestamp="2010-01-01",
                voltage=-1.0,
                pump="media",
            )
        )
        cache["alt_media"] = encode(
            structs.AltMediaPumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                timestamp="2010-01-01",
                voltage=-1.0,
                pump="alt_media",
            )
        )
        cache["waste"] = encode(
            structs.WastePumpCalibration(
                name="setup_function",
                duration_=1.0,
                bias_=0,
                dc=60,
                hz=100,
                timestamp="2010-01-01",
                voltage=-1.0,
                pump="waste",
            )
        )


def test_silent_automation() -> None:
    experiment = "test_silent_automation"
    with Silent(volume=None, duration=60, unit=unit, experiment=experiment) as algo:
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
        )
        pause()
        assert isinstance(algo.run(), events.NoEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.02, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 1.1, "timestamp": current_utc_timestamp()}),
        )
        pause()
        assert isinstance(algo.run(), events.NoEvent)


def test_turbidostat_automation() -> None:
    experiment = "test_turbidostat_automation"
    target_od = 1.0
    with Turbidostat(
        target_normalized_od=target_od, duration=60, volume=0.25, unit=unit, experiment=experiment
    ) as algo:

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 0.98, "timestamp": current_utc_timestamp()}),
        )
        pause()

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 1.01, "timestamp": current_utc_timestamp()}),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 0.99, "timestamp": current_utc_timestamp()}),
        )
        pause()
        assert algo.run() is None


def test_morbidostat_automation() -> None:
    experiment = "test_morbidostat_automation"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        None,
        retain=True,
    )

    target_od = 1.0
    algo = Morbidostat(
        target_normalized_od=target_od, duration=60, volume=0.25, unit=unit, experiment=experiment
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.99, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.05, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.AddAltMediaEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.03, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.04, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.AddAltMediaEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.01, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.99, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.DilutionEvent)
    algo.clean_up()


def test_pid_morbidostat_automation() -> None:
    experiment = "test_pid_morbidostat_automation"
    target_growth_rate = 0.09
    algo = PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=target_growth_rate,
        duration=60,
        unit=unit,
        experiment=experiment,
    )

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.5, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.NoEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.AddAltMediaEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.07, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.AddAltMediaEvent)
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.065, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    assert isinstance(algo.run(), events.AddAltMediaEvent)
    algo.clean_up()


def test_changing_morbidostat_parameters_over_mqtt() -> None:
    experiment = "test_changing_morbidostat_parameters_over_mqtt"
    target_growth_rate = 0.05
    algo = PIDMorbidostat(
        target_growth_rate=target_growth_rate,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.target_growth_rate == target_growth_rate
    pause()
    new_target = 0.07
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/target_growth_rate/set",
        new_target,
    )
    pause()
    assert algo.target_growth_rate == new_target
    assert algo.pid.pid.setpoint == new_target
    algo.clean_up()


def test_changing_turbidostat_params_over_mqtt() -> None:
    experiment = "test_changing_turbidostat_params_over_mqtt"
    og_volume = 0.5
    og_target_od = 1.0
    algo = Turbidostat(
        volume=og_volume,
        target_normalized_od=og_target_od,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.volume == og_volume

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.05, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
    )
    pause()
    algo.run()

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/volume/set", 1.0)
    pause()

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.05, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
    )
    algo.run()

    assert algo.volume == 1.0

    new_od = 1.5
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/target_normalized_od/set", new_od
    )
    pause()
    assert algo.target_normalized_od == new_od
    algo.clean_up()


def test_changing_parameters_over_mqtt_with_unknown_parameter() -> None:
    experiment = "test_changing_parameters_over_mqtt_with_unknown_parameter"
    with pubsub.collect_all_logs_of_level("DEBUG", unit, experiment) as bucket:
        with DosingAutomationJob(
            target_growth_rate=0.05,
            target_od=1.0,
            duration=60,
            unit=unit,
            experiment=experiment,
        ):

            pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/garbage/set", 0.07)
            # there should be a log published with "Unable to set garbage in dosing_automation"
            pause()
            pause()
            pause()

    assert len(bucket) > 0
    assert any(["garbage" in log["message"] for log in bucket])


def test_pause_in_dosing_automation() -> None:
    experiment = "test_pause_in_dosing_automation"
    with DosingAutomationJob(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        pause()
        pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "sleeping")
        pause()
        assert algo.state == "sleeping"

        pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "ready")
        pause()
        assert algo.state == "ready"


def test_pause_in_dosing_control_also_pauses_automation() -> None:
    experiment = "test_pause_in_dosing_control_also_pauses_automation"
    algo = DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    )
    pause()
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "sleeping")
    pause()
    assert algo.state == "sleeping"
    assert algo.automation_job.state == "sleeping"

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "ready")
    pause()
    assert algo.state == "ready"
    assert algo.automation_job.state == "ready"
    algo.clean_up()


def test_old_readings_will_not_execute_io() -> None:
    experiment = "test_old_readings_will_not_execute_io"
    with DosingAutomationJob(
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        algo._latest_growth_rate = 1
        algo._latest_normalized_od = 1

        algo.latest_normalized_od_at = datetime.utcnow() - timedelta(minutes=10)
        algo.latest_growth_rate_at = datetime.utcnow() - timedelta(minutes=4)

        assert algo.most_stale_time == algo.latest_normalized_od_at

        assert isinstance(algo.run(), events.NoEvent)


def test_throughput_calculator() -> None:
    experiment = "test_throughput_calculator"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    algo = DosingController(
        "pid_morbidostat",
        target_growth_rate=0.05,
        target_od=1.0,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.automation_job.media_throughput == 0
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
    )
    pause()
    algo.automation_job.run()

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    algo.automation_job.run()
    assert algo.automation_job.media_throughput > 0
    assert algo.automation_job.alt_media_throughput > 0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.07, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    algo.automation_job.run()
    assert algo.automation_job.media_throughput > 0
    assert algo.automation_job.alt_media_throughput > 0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.065, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    pause()
    algo.automation_job.run()
    assert algo.automation_job.media_throughput > 0
    assert algo.automation_job.alt_media_throughput > 0
    algo.clean_up()


def test_throughput_calculator_restart() -> None:
    experiment = "test_throughput_calculator_restart"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = str(1.0)

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = str(1.5)

    with DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    ) as algo:
        pause()
        assert algo.automation_job.media_throughput == 1.0
        assert algo.automation_job.alt_media_throughput == 1.5


def test_throughput_calculator_manual_set() -> None:
    experiment = "test_throughput_calculator_manual_set"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = str(1.0)

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = str(1.5)

    with DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    ) as algo:

        pause()
        assert algo.automation_job.media_throughput == 1.0
        assert algo.automation_job.alt_media_throughput == 1.5

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_throughput/set",
            0,
        )
        pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/media_throughput/set", 0)
        pause()
        pause()
        assert algo.automation_job.media_throughput == 0
        assert algo.automation_job.alt_media_throughput == 0


def test_execute_io_action() -> None:
    experiment = "test_execute_io_action"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with DosingController("silent", unit=unit, experiment=experiment) as ca:
        ca.automation_job.execute_io_action(media_ml=0.65, alt_media_ml=0.35, waste_ml=0.65 + 0.35)
        pause()
        assert ca.automation_job.media_throughput == 0.65
        assert ca.automation_job.alt_media_throughput == 0.35

        ca.automation_job.execute_io_action(media_ml=0.15, alt_media_ml=0.15, waste_ml=0.3)
        pause()
        assert ca.automation_job.media_throughput == 0.80
        assert ca.automation_job.alt_media_throughput == 0.50

        ca.automation_job.execute_io_action(media_ml=1.0, alt_media_ml=0, waste_ml=1)
        pause()
        assert ca.automation_job.media_throughput == 1.80
        assert ca.automation_job.alt_media_throughput == 0.50

        ca.automation_job.execute_io_action(media_ml=0.0, alt_media_ml=1.0, waste_ml=1)
        pause()
        assert ca.automation_job.media_throughput == 1.80
        assert ca.automation_job.alt_media_throughput == 1.50


def test_execute_io_action2() -> None:
    experiment = "test_execute_io_action2"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    with DosingController("silent", unit=unit, experiment=experiment) as ca:
        ca.automation_job.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
        pause()
        assert ca.automation_job.media_throughput == 1.25
        assert ca.automation_job.alt_media_throughput == 0.01
        assert abs(ca.automation_job.alt_media_fraction - 0.0007142) < 0.000001


def test_execute_io_action_outputs1() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs1"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    ca = DosingAutomationJob(unit=unit, experiment=experiment)
    result = ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
    assert result[0] == 1.25
    assert result[1] == 0.01
    assert result[2] == 1.26
    ca.clean_up()


def test_execute_io_action_outputs_will_be_null_if_calibration_is_not_defined() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs_will_be_null_if_calibration_is_not_defined"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("pump_calibrations") as cache:
        del cache["media"]
        del cache["alt_media"]

    with pytest.raises(exc.CalibrationError):
        with DosingAutomationJob(unit=unit, experiment=experiment, skip_first_run=True) as ca:
            ca.execute_io_action(media_ml=0.1, alt_media_ml=0.1, waste_ml=0.2)

    # add back to cache
    with local_persistant_storage("pump_calibrations") as cache:
        cache["media"] = json.dumps({"duration_": 1.0})
        cache["alt_media"] = json.dumps({"duration_": 1.0})


def test_execute_io_action_outputs_will_shortcut_if_disconnected() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs_will_shortcut_if_disconnected"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    ca = DosingAutomationJob(unit=unit, experiment=experiment)
    ca.clean_up()
    result = ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
    assert result[0] == 0.0
    assert result[1] == 0.0
    assert result[2] == 0.0


def test_PIDMorbidostat() -> None:
    experiment = "test_PIDMorbidostat"
    algo = PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.latest_event is None
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.5, "timestamp": current_utc_timestamp()}),
    )
    time.sleep(10)
    pause()
    assert isinstance(algo.latest_event, events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 0.95, "timestamp": current_utc_timestamp()}),
    )
    time.sleep(20)
    pause()
    assert isinstance(algo.latest_event, events.AddAltMediaEvent)
    algo.clean_up()


def test_changing_duration_over_mqtt() -> None:
    experiment = "test_changing_duration_over_mqtt"
    with PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.latest_event is None
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 0.5, "timestamp": current_utc_timestamp()}),
        )
        time.sleep(10)

        assert isinstance(algo.latest_event, events.NoEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_automation/duration/set",
            1,  # in minutes
        )
        time.sleep(10)
        assert algo.run_thread.interval == 60  # in seconds


def test_changing_duration_over_mqtt_will_start_next_run_earlier() -> None:
    experiment = "test_changing_duration_over_mqtt_will_start_next_run_earlier"
    with PIDMorbidostat(
        target_od=1.0,
        target_growth_rate=0.01,
        duration=10 / 60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.latest_event is None
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            json.dumps({"growth_rate": 0.08, "timestamp": current_utc_timestamp()}),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            json.dumps({"od_filtered": 0.5, "timestamp": current_utc_timestamp()}),
        )
        time.sleep(15)

        assert isinstance(algo.latest_event, events.NoEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_automation/duration/set",
            15 / 60,  # in minutes
        )
        time.sleep(5)
        assert algo.run_thread.interval == 15  # in seconds
        assert algo.run_thread.run_after > 0


def test_changing_algo_over_mqtt_with_wrong_automation_type() -> None:
    experiment = "test_changing_algo_over_mqtt_with_wrong_automation_type"
    with DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.automation.automation_name == "turbidostat"
        assert isinstance(algo.automation_job, Turbidostat)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_control/automation/set",
            json.dumps(
                {
                    "automation_name": "pid_morbidostat",
                    "type": "led",
                    "args": {
                        "duration": 60,
                        "target_od": 1.0,
                        "target_growth_rate": 0.07,
                    },
                }
            ),
        )
        time.sleep(8)
        assert algo.automation.automation_name == "turbidostat"


def test_changing_algo_over_mqtt_solo() -> None:
    experiment = "test_changing_algo_over_mqtt_solo"
    with DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.automation.automation_name == "turbidostat"
        assert isinstance(algo.automation_job, Turbidostat)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_control/automation/set",
            json.dumps(
                {
                    "automation_name": "pid_morbidostat",
                    "type": "dosing",
                    "args": {
                        "duration": 60,
                        "target_od": 1.0,
                        "target_growth_rate": 0.07,
                    },
                }
            ),
        )
        time.sleep(8)
        assert algo.automation.automation_name == "pid_morbidostat"
        assert isinstance(algo.automation_job, PIDMorbidostat)
        assert algo.automation_job.target_growth_rate == 0.07


@pytest.mark.skip(reason="this doesn't clean up properly")
def test_changing_algo_over_mqtt_when_it_fails_will_rollback() -> None:
    experiment = "test_changing_algo_over_mqtt_when_it_fails_will_rollback"
    with DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.automation.automation_name == "turbidostat"
        assert isinstance(algo.automation_job, Turbidostat)
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_control/automation/set",
            json.dumps(
                {
                    "automation_name": "pid_morbidostat",
                    "args": {"duration": 60},
                    "type": "dosing",
                }
            ),
        )
        time.sleep(10)
        assert algo.automation.automation_name == "turbidostat"
        assert isinstance(algo.automation_job, Turbidostat)
        assert algo.automation_job.target_normalized_od == 1.0
        pause()
        pause()
        pause()


def test_changing_algo_over_mqtt_will_not_produce_two_dosing_jobs() -> None:
    experiment = "test_changing_algo_over_mqtt_will_not_produce_two_dosing_jobs"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = "0.0"

    with local_persistant_storage("alt_media_fraction") as c:
        c[experiment] = "0.0"

    algo = DosingController(
        "turbidostat",
        volume=1.0,
        target_normalized_od=0.4,
        duration=60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.automation.automation_name == "turbidostat"
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/automation/set",
        json.dumps(
            {
                "automation_name": "turbidostat",
                "type": "dosing",
                "args": {
                    "duration": 60,
                    "target_normalized_od": 1.0,
                    "volume": 1.0,
                    "skip_first_run": 1,
                },
            }
        ),
    )
    time.sleep(10)  # need to wait for all jobs to disconnect correctly and threads to join.
    assert isinstance(algo.automation_job, Turbidostat)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        json.dumps({"growth_rate": 1.0, "timestamp": current_utc_timestamp()}),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        json.dumps({"od_filtered": 1.0, "timestamp": current_utc_timestamp()}),
    )
    pause()

    # note that we manually run, as we have skipped the first run in the json
    algo.automation_job.run()
    time.sleep(5)
    assert algo.automation_job.media_throughput == 1.0

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_automation/target_normalized_od/set", 1.5
    )
    pause()
    pause()
    assert algo.automation_job.target_normalized_od == 1.5
    algo.clean_up()


def test_changing_algo_over_mqtt_with_wrong_type_is_okay() -> None:
    experiment = "test_changing_algo_over_mqtt_with_wrong_type_is_okay"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = "0.0"

    algo = DosingController(
        "turbidostat",
        volume=1.0,
        target_normalized_od=0.4,
        duration=2 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.automation.automation_name == "turbidostat"
    assert algo.automation_name == "turbidostat"
    pause()
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/dosing_control/automation/set",
        json.dumps(
            {
                "automation_name": "turbidostat",
                "type": "dosing",
                "args": {"duration": "60", "target_normalized_od": "1.0", "volume": "1.0"},
            }
        ),
    )
    time.sleep(7)  # need to wait for all jobs to disconnect correctly and threads to join.
    assert isinstance(algo.automation_job, Turbidostat)
    assert algo.automation_job.target_normalized_od == 1.0
    algo.clean_up()


def test_disconnect_cleanly() -> None:
    experiment = "test_disconnect_cleanly"
    algo = DosingController(
        "turbidostat",
        target_normalized_od=1.0,
        duration=50,
        unit=unit,
        volume=1.0,
        experiment=experiment,
    )
    assert algo.automation.automation_name == "turbidostat"
    assert isinstance(algo.automation_job, Turbidostat)
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "disconnected")
    time.sleep(10)
    assert algo.state == algo.DISCONNECTED


def test_disconnect_cleanly_during_pumping_execution() -> None:
    experiment = "test_disconnect_cleanly_during_pumping_execution"
    algo = DosingController(
        "chemostat",
        volume=5.0,
        duration=10,
        unit=unit,
        experiment=experiment,
    )
    assert algo.automation.automation_name == "chemostat"
    time.sleep(4)
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_control/$state/set", "disconnected")
    time.sleep(10)
    assert algo.state == algo.DISCONNECTED
    assert algo.automation_job.state == algo.DISCONNECTED


def test_custom_class_will_register_and_run() -> None:
    experiment = "test_custom_class_will_register_and_run"

    class NaiveTurbidostat(DosingAutomationJob):

        automation_name = "naive_turbidostat"
        published_settings = {
            "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
            "duration": {"datatype": "float", "settable": True, "unit": "min"},
        }

        def __init__(self, target_od: float, **kwargs: Any) -> None:
            super(NaiveTurbidostat, self).__init__(**kwargs)
            self.target_od = target_od

        def execute(self) -> None:
            if self.latest_normalized_od > self.target_od:
                self.execute_io_action(media_ml=1.0, waste_ml=1.0)

    with DosingController(
        "naive_turbidostat",
        target_od=2.0,
        duration=10,
        unit=get_unit_name(),
        experiment=experiment,
    ):
        pass


def test_what_happens_when_no_od_data_is_coming_in() -> None:
    experiment = "test_what_happens_when_no_od_data_is_coming_in"
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        None,
        retain=True,
    )

    algo = Turbidostat(
        target_normalized_od=0.1, duration=40 / 60, volume=0.25, unit=unit, experiment=experiment
    )
    pause()
    event = algo.run()
    assert isinstance(event, events.ErrorOccurred)
    algo.clean_up()


def test_changing_duty_cycle_over_mqtt() -> None:
    experiment = "test_changing_duty_cycle_over_mqtt"
    with ContinuousCycle(unit=unit, experiment=experiment) as algo:

        assert algo.duty_cycle == 100
        pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/duty_cycle/set", 50)
        pause()
        assert algo.duty_cycle == 50


def test_AltMediaCalculator() -> None:
    from pioreactor.structs import DosingEvent

    ac = AltMediaCalculator()

    data = DosingEvent(volume_change=1.0, event="add_media", timestamp="0", source_of_event="test")
    assert 0.0 == ac.update(data, 0.0)

    data = DosingEvent(
        volume_change=1.0, event="add_alt_media", timestamp="1", source_of_event="test"
    )
    assert 1 / 14.0 == 0.07142857142857142 == ac.update(data, 0.0)

    data = DosingEvent(
        volume_change=1.0, event="add_alt_media", timestamp="2", source_of_event="test"
    )
    assert 0.13775510204081634 == ac.update(data, 1 / 14.0) < 2 / 14.0


def test_latest_event_goes_to_mqtt():
    experiment = "test_latest_event_goes_to_mqtt"

    class FakeAutomation(DosingAutomationJob):
        """
        Do nothing, ever. Just pass.
        """

        automation_name = "fake_automation"
        published_settings = {"duration": {"datatype": "float", "settable": True, "unit": "min"}}

        def __init__(self, **kwargs) -> None:
            super(FakeAutomation, self).__init__(**kwargs)

        def execute(self):
            return events.NoEvent(message="demo", data={"d": 1.0, "s": "test"})

    with DosingController(
        "fake_automation",
        duration=0.1,
        unit=get_unit_name(),
        experiment=experiment,
    ) as dc:
        assert "latest_event" in dc.automation_job.published_settings

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/latest_event")
        assert msg is not None

        latest_event_from_mqtt = json.loads(msg.payload)
        assert latest_event_from_mqtt["event_name"] == "NoEvent"
        assert latest_event_from_mqtt["message"] == "demo"
        assert latest_event_from_mqtt["data"]["d"] == 1.0
        assert latest_event_from_mqtt["data"]["s"] == "test"
