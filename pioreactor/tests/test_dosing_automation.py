# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from threading import Timer
from typing import Any

import pytest
from click.testing import CliRunner
from msgspec.json import encode

from pioreactor import exc
from pioreactor import pubsub
from pioreactor import structs
from pioreactor.automations import events
from pioreactor.automations.dosing.chemostat import Chemostat
from pioreactor.automations.dosing.pid_morbidostat import PIDMorbidostat
from pioreactor.automations.dosing.silent import Silent
from pioreactor.automations.dosing.turbidostat import Turbidostat
from pioreactor.background_jobs.dosing_automation import AltMediaFractionCalculator
from pioreactor.background_jobs.dosing_automation import close
from pioreactor.background_jobs.dosing_automation import DosingAutomationJob
from pioreactor.background_jobs.dosing_automation import start_dosing_automation
from pioreactor.background_jobs.dosing_automation import VialVolumeCalculator
from pioreactor.structs import DosingEvent
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import default_datetime_for_pioreactor
from pioreactor.whoami import get_unit_name


unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions when updating state
    time.sleep(n * 0.5)


def setup_function() -> None:
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
                durations=[0, 1],
                volumes=[0, 1.5],
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
                durations=[0, 1],
                volumes=[0, 1.5],
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
                durations=[0, 1],
                volumes=[0, 1.5],
                pioreactor_unit=unit,
            )
        )


def test_silent_automation() -> None:
    experiment = "test_silent_automation"
    with Silent(volume=None, duration=60, unit=unit, experiment=experiment) as algo:
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.05, channel="2"
                        )
                    },
                )
            ),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
        )
        pause()
        assert algo.run() is None
        assert algo.latest_normalized_od == 1.0
        assert algo.latest_growth_rate == 0.01
        assert algo.latest_od == {"2": 0.05}

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.06, channel="2"
                        )
                    },
                )
            ),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.02, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.1, timestamp=current_utc_datetime())),
        )
        pause()
        assert algo.run() is None
        assert algo.latest_normalized_od == 1.1
        assert algo.previous_normalized_od == 1.0

        assert algo.latest_growth_rate == 0.02
        assert algo.previous_growth_rate == 0.01

        assert algo.latest_od == {"2": 0.06}
        assert algo.previous_od == {"2": 0.05}


def test_turbidostat_automation() -> None:
    experiment = "test_turbidostat_automation"
    target_od = 1.0
    with Turbidostat(
        target_normalized_od=target_od,
        duration=60,
        volume=0.25,
        unit=unit,
        experiment=experiment,
        skip_first_run=True,
    ) as algo:
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.98, timestamp=current_utc_datetime())),
        )
        pause()

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.01, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.01, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.99, timestamp=current_utc_datetime())),
        )
        pause()
        assert algo.run() is None


def test_cant_target_both_in_turbidostat() -> None:
    experiment = "test_cant_target_both_in_turbidostat"

    with pytest.raises(ValueError):
        with Turbidostat(
            target_od=0.5,
            target_normalized_od=2.0,
            duration=60,
            volume=0.25,
            unit=unit,
            experiment=experiment,
            skip_first_run=True,
        ):
            pass


def test_cant_change_target_in_turbidostat() -> None:
    experiment = "test_cant_change_target_in_turbidostat"

    with Turbidostat(
        target_od=0.5,
        duration=60,
        volume=0.25,
        unit=unit,
        experiment=experiment,
        skip_first_run=True,
    ) as algo:
        assert not algo.is_targeting_nOD
        assert algo.target_od == 0.5
        assert algo.target_normalized_od is None

        algo.set_target_normalized_od(2.0)

        assert not algo.is_targeting_nOD
        assert algo.target_od == 0.5
        assert algo.target_normalized_od is None


def test_turbidostat_targeting_od() -> None:
    experiment = "test_turbidostat_targeting_od"

    target_od = 0.2
    with Turbidostat(
        target_od=target_od,
        duration=60,
        volume=0.25,
        unit=unit,
        experiment=experiment,
        skip_first_run=True,
    ) as algo:
        assert algo.target_od == target_od
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.05, channel="2"
                        )
                    },
                )
            ),
        )
        pause()

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.250, channel="2"
                        )
                    },
                )
            ),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.500, channel="2"
                        )
                    },
                )
            ),
        )
        pause()
        assert isinstance(algo.run(), events.DilutionEvent)

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/od_reading/ods",
            encode(
                structs.ODReadings(
                    timestamp=current_utc_datetime(),
                    ods={
                        "2": structs.ODReading(
                            timestamp=current_utc_datetime(), angle="45", od=0.100, channel="2"
                        )
                    },
                )
            ),
        )
        pause()
        assert algo.run() is None

        assert algo.media_throughput == 0.50


def test_pid_morbidostat_automation() -> None:
    experiment = "test_pid_morbidostat_automation"
    target_growth_rate = 0.09
    with PIDMorbidostat(
        target_normalized_od=1.0,
        target_growth_rate=target_growth_rate,
        duration=60,
        skip_first_run=True,
        unit=unit,
        experiment=experiment,
    ) as algo:
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.5, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.NoEvent)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.AddAltMediaEvent)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.07, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.AddAltMediaEvent)
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.065, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        assert isinstance(algo.run(), events.AddAltMediaEvent)


def test_changing_morbidostat_parameters_over_mqtt() -> None:
    experiment = "test_changing_morbidostat_parameters_over_mqtt"
    target_growth_rate = 0.05
    algo = PIDMorbidostat(
        target_growth_rate=target_growth_rate,
        target_normalized_od=1.0,
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
    assert algo.pid.setpoint == new_target
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
        skip_first_run=True,
    )
    assert algo.volume == og_volume

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        encode(structs.GrowthRate(growth_rate=0.05, timestamp=current_utc_datetime())),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
    )
    pause()
    algo.run()

    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/volume/set", 1.0)
    pause()

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        encode(structs.GrowthRate(growth_rate=0.05, timestamp=current_utc_datetime())),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
    )
    algo.run()

    assert algo.volume == 1.0

    new_od = 1.5
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/target_normalized_od/set", new_od)
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
            pause(2)
            pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/garbage/set", 0.07)
            # there should be a log published with "Unable to set garbage in dosing_automation"
            pause(2)
        pause(2)

    assert len(bucket) > 0
    assert any(["garbage" in log["message"] for log in bucket])


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

        algo.latest_normalized_od_at = current_utc_datetime() - timedelta(minutes=10)
        algo.latest_growth_rate_at = current_utc_datetime() - timedelta(minutes=4)

        assert algo.most_stale_time == algo.latest_normalized_od_at

        assert isinstance(algo.run(), events.NoEvent)


def test_throughput_calculator_multiple_types() -> None:
    experiment = "test_throughput_calculator_multiple_types"

    with PIDMorbidostat(
        unit=unit,
        experiment=experiment,
        target_growth_rate=0.05,
        target_normalized_od=1.0,
        duration=60,
        skip_first_run=True,
    ) as algo:
        assert algo.media_throughput == 0
        pause()
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=1.0, timestamp=current_utc_datetime())),
        )
        pause()
        algo.run()

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        algo.run()
        assert algo.media_throughput > 0
        assert algo.alt_media_throughput > 0

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.07, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        algo.run()
        assert algo.media_throughput > 0
        assert algo.alt_media_throughput > 0

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.065, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
        )
        pause()
        algo.run()
        assert algo.media_throughput > 0
        assert algo.alt_media_throughput > 0


def test_throughput_calculator_restart() -> None:
    experiment = "test_throughput_calculator_restart"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = 1.0

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = 1.5

    with Turbidostat(
        unit=unit,
        experiment=experiment,
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
    ) as automation_job:
        pause()
        assert automation_job.media_throughput == 1.0
        assert automation_job.alt_media_throughput == 1.5


def test_throughput_calculator_manual_set() -> None:
    experiment = "test_throughput_calculator_manual_set"
    with local_persistant_storage("media_throughput") as c:
        c[experiment] = 1.0

    with local_persistant_storage("alt_media_throughput") as c:
        c[experiment] = 1.5

    with Turbidostat(
        unit=unit,
        experiment=experiment,
        target_normalized_od=1.0,
        duration=5 / 60,
        volume=1.0,
    ) as automation_job:
        pause()
        assert automation_job.media_throughput == 1.0
        assert automation_job.alt_media_throughput == 1.5

        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_throughput/set",
            0,
        )
        pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/media_throughput/set", 0)
        pause()
        pause()
        assert automation_job.media_throughput == 0
        assert automation_job.alt_media_throughput == 0


def test_execute_io_action() -> None:
    experiment = "test_execute_io_action"

    with Silent(unit=unit, experiment=experiment) as ca:
        ca.execute_io_action(media_ml=0.50, alt_media_ml=0.35, waste_ml=0.50 + 0.35)
        pause()
        assert ca.media_throughput == 0.50
        assert ca.alt_media_throughput == 0.35

        ca.execute_io_action(media_ml=0.15, alt_media_ml=0.15, waste_ml=0.3)
        pause()
        assert ca.media_throughput == 0.65
        assert ca.alt_media_throughput == 0.50

        ca.execute_io_action(media_ml=0.6, alt_media_ml=0, waste_ml=0.6)
        pause()
        assert ca.media_throughput == 1.25
        assert ca.alt_media_throughput == 0.50

        ca.execute_io_action(media_ml=0.0, alt_media_ml=0.6, waste_ml=0.6)
        pause()
        assert ca.media_throughput == 1.25
        assert ca.alt_media_throughput == 1.1

        ca.execute_io_action(media_ml=0.0, alt_media_ml=0.0, waste_ml=0.0)
        pause()
        assert ca.media_throughput == 1.25
        assert ca.alt_media_throughput == 1.1


def test_execute_io_action2() -> None:
    experiment = "test_execute_io_action2"

    with Silent(unit=unit, experiment=experiment, initial_vial_volume=14.0) as ca:
        results = ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
        pause()
        assert results["media_ml"] == 1.25
        assert results["alt_media_ml"] == 0.01
        assert results["waste_ml"] == 1.26
        assert ca.media_throughput == 1.25
        assert ca.alt_media_throughput == 0.01
        assert close(ca.alt_media_fraction, 0.0006688099108144436)


def test_execute_io_action_outputs1() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs1"

    with DosingAutomationJob(unit=unit, experiment=experiment) as ca:
        result = ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
        assert result["media_ml"] == 1.25
        assert result["alt_media_ml"] == 0.01
        assert result["waste_ml"] == 1.26


def test_execute_io_action_outputs_float_point_error() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs1"

    with DosingAutomationJob(unit=unit, experiment=experiment) as ca:
        media = 0.1
        waste = 1.2 - 1.1  # should be ~0.09999999999999987
        assert waste < 0.1

        result = ca.execute_io_action(media_ml=media, waste_ml=waste)
        assert result["media_ml"] == media
        assert result["waste_ml"] == waste


def test_mqtt_properties_in_dosing_automations() -> None:
    experiment = "test_mqtt_properties_in_dosing_automations"

    with DosingAutomationJob(unit=unit, experiment=experiment) as ca:
        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_throughput")
        assert msg is not None
        r = msg.payload
        assert float(r) == 0

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/media_throughput")
        assert msg is not None
        r = msg.payload
        assert float(r) == 0

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_fraction")
        assert msg is not None
        r = msg.payload
        assert float(r) == 0

        ca.execute_io_action(media_ml=0.35, alt_media_ml=0.25, waste_ml=0.6)

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_throughput")
        assert msg is not None
        r = msg.payload
        assert float(r) == 0.25

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/media_throughput")
        assert msg is not None
        r = msg.payload
        assert float(r) == 0.35

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/alt_media_fraction")
        assert msg is not None
        r = msg.payload
        assert close(float(r), 0.017123287671232876)


def test_execute_io_action_outputs_will_be_null_if_calibration_is_not_defined() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs_will_be_null_if_calibration_is_not_defined"

    with local_persistant_storage("current_pump_calibration") as cache:
        del cache["media"]
        del cache["alt_media"]

    with pytest.raises(exc.CalibrationError):
        with DosingAutomationJob(unit=unit, experiment=experiment, skip_first_run=True) as ca:
            ca.execute_io_action(media_ml=0.1, alt_media_ml=0.1, waste_ml=0.2)


def test_execute_io_action_outputs_will_shortcut_if_disconnected() -> None:
    # regression test
    experiment = "test_execute_io_action_outputs_will_shortcut_if_disconnected"

    ca = DosingAutomationJob(unit=unit, experiment=experiment)
    ca.clean_up()
    result = ca.execute_io_action(media_ml=1.25, alt_media_ml=0.01, waste_ml=1.26)
    assert result["media_ml"] == 0.0
    assert result["alt_media_ml"] == 0.0
    assert result["waste_ml"] == 0.0


def test_PIDMorbidostat() -> None:
    experiment = "test_PIDMorbidostat"
    algo = PIDMorbidostat(
        target_normalized_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    )
    assert algo.latest_event is None
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        encode(structs.ODFiltered(od_filtered=0.5, timestamp=current_utc_datetime())),
    )
    time.sleep(10)
    pause()
    assert isinstance(algo.latest_event, events.NoEvent)

    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
    )
    pubsub.publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
        encode(structs.ODFiltered(od_filtered=0.95, timestamp=current_utc_datetime())),
    )
    time.sleep(20)
    pause()
    assert isinstance(algo.latest_event, events.AddAltMediaEvent)
    algo.clean_up()


def test_changing_duration_over_mqtt() -> None:
    experiment = "test_changing_duration_over_mqtt"
    with PIDMorbidostat(
        target_normalized_od=1.0,
        target_growth_rate=0.01,
        duration=5 / 60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.latest_event is None
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.5, timestamp=current_utc_datetime())),
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
        target_normalized_od=1.0,
        target_growth_rate=0.01,
        duration=10 / 60,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert algo.latest_event is None
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
            encode(structs.GrowthRate(growth_rate=0.08, timestamp=current_utc_datetime())),
        )
        pubsub.publish(
            f"pioreactor/{unit}/{experiment}/growth_rate_calculating/od_filtered",
            encode(structs.ODFiltered(od_filtered=0.5, timestamp=current_utc_datetime())),
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


def test_disconnect_cleanly() -> None:
    experiment = "test_disconnect_cleanly"
    algo = Turbidostat(
        unit=unit,
        experiment=experiment,
        target_normalized_od=1.0,
        duration=50,
        volume=1.0,
    )
    assert algo.automation_name == "turbidostat"
    assert isinstance(algo, Turbidostat)
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "disconnected")
    time.sleep(10)
    assert algo.state == algo.DISCONNECTED


def test_disconnect_cleanly_during_pumping_execution() -> None:
    experiment = "test_disconnect_cleanly_during_pumping_execution"
    algo = Chemostat(
        unit=unit,
        experiment=experiment,
        volume=5.0,
        duration=10,
    )
    assert algo.automation_name == "chemostat"
    time.sleep(4)
    pubsub.publish(f"pioreactor/{unit}/{experiment}/dosing_automation/$state/set", "disconnected")
    time.sleep(10)
    assert algo.state == algo.DISCONNECTED


def test_custom_class_will_register_and_run() -> None:
    experiment = "test_custom_class_will_register_and_run"

    class NaiveTurbidostat(DosingAutomationJob):
        automation_name = "_test_naive_turbidostat"
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

    with NaiveTurbidostat(
        unit=get_unit_name(),
        experiment=experiment,
        target_od=2.0,
        duration=10,
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

    with Turbidostat(
        target_normalized_od=0.1, duration=40 / 60, volume=0.25, unit=unit, experiment=experiment
    ) as algo:
        pause()
        event = algo.run()
        assert isinstance(event, events.ErrorOccurred)


def test_AltMediaFractionCalculator() -> None:
    ac = AltMediaFractionCalculator()
    vial_volume = 14

    media_added = 1.0
    add_media_event = DosingEvent(
        volume_change=media_added,
        event="add_media",
        timestamp=default_datetime_for_pioreactor(0),
        source_of_event="test",
    )
    assert ac.update(add_media_event, 0.0, vial_volume) == 0.0
    assert close(ac.update(add_media_event, 0.20, vial_volume), 0.18666666666666668)
    assert close(ac.update(add_media_event, 1.0, vial_volume), 0.9333333333333333)

    alt_media_added = 1.0
    add_alt_media_event = DosingEvent(
        volume_change=alt_media_added,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(1),
        source_of_event="test",
    )
    assert ac.update(add_alt_media_event, 0.0, vial_volume) == 1 / (vial_volume + 1)

    alt_media_added = 2.0
    add_alt_media_event = DosingEvent(
        volume_change=alt_media_added,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(2),
        source_of_event="test",
    )
    assert ac.update(add_alt_media_event, 0.0, vial_volume) == 2 / (vial_volume + 2)

    alt_media_added = vial_volume
    add_alt_media_event = DosingEvent(
        volume_change=alt_media_added,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(3),
        source_of_event="test",
    )
    assert ac.update(add_alt_media_event, 0, vial_volume) == 0.5

    add_alt_media_event = DosingEvent(
        volume_change=alt_media_added,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(4),
        source_of_event="test",
    )
    assert ac.update(add_alt_media_event, 0.5, vial_volume) == 0.75


def test_latest_event_goes_to_mqtt() -> None:
    experiment = "test_latest_event_goes_to_mqtt"

    class FakeAutomation(DosingAutomationJob):
        """
        Do nothing, ever. Just pass.
        """

        automation_name = "_test_fake_automation"
        published_settings = {"duration": {"datatype": "float", "settable": True, "unit": "min"}}

        def __init__(self, **kwargs) -> None:
            super(FakeAutomation, self).__init__(**kwargs)

        def execute(self):
            return events.NoEvent(message="demo", data={"d": 1.0, "s": "test"})

    with FakeAutomation(
        unit=get_unit_name(),
        experiment=experiment,
        duration=0.1,
    ) as dc:
        assert "latest_event" in dc.published_settings

        msg = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/latest_event")
        assert msg is not None

        latest_event_from_mqtt = json.loads(msg.payload)
        assert latest_event_from_mqtt["event_name"] == "NoEvent"
        assert latest_event_from_mqtt["message"] == "demo"
        assert latest_event_from_mqtt["data"]["d"] == 1.0
        assert latest_event_from_mqtt["data"]["s"] == "test"


def test_strings_are_okay_for_chemostat() -> None:
    unit = get_unit_name()
    experiment = "test_strings_are_okay_for_chemostat"

    with start_dosing_automation("chemostat", "20", False, unit, experiment, volume="0.7") as chemostat:  # type: ignore
        assert chemostat.volume == 0.7  # type: ignore
        pause(n=35)
        assert chemostat.media_throughput == 0.7


def test_chemostat_from_cli() -> None:
    from pioreactor.cli.pio import pio

    t = Timer(
        15,
        pubsub.publish,
        args=(
            "pioreactor/testing_unit/_testing_experiment/dosing_automation/$state/set",
            "disconnected",
        ),
    )
    t.start()

    with pubsub.collect_all_logs_of_level("ERROR", "testing_unit", "_testing_experiment") as errors:
        runner = CliRunner()
        result = runner.invoke(
            pio, ["run", "dosing_automation", "--automation-name", "chemostat", "--volume", "1.5"]
        )

    assert result.exit_code == 0
    assert len(errors) == 0


def test_pass_in_initial_alt_media_fraction() -> None:
    experiment = "test_pass_in_initial_alt_media_fraction"
    unit = get_unit_name()

    with start_dosing_automation(
        "chemostat", 20, False, unit, experiment, volume=0.25, initial_alt_media_fraction=0.5
    ) as chemostat:
        assert chemostat.alt_media_fraction == 0.5
        pause(n=35)
        alt_media_fraction_post_dosing = 0.5 / (1 + 0.25 / chemostat.vial_volume)
        assert chemostat.media_throughput == 0.25
        assert chemostat.alt_media_throughput == 0.0
        assert close(chemostat.alt_media_fraction, alt_media_fraction_post_dosing)

    # test that the latest alt_media_fraction is saved and reused if dosing automation is recreated in the same experiment.
    with start_dosing_automation(
        "chemostat",
        20,
        False,
        unit,
        experiment,
        volume=0.35,
    ) as chemostat:
        assert close(chemostat.alt_media_fraction, alt_media_fraction_post_dosing)
        pause(n=35)
        assert close(
            chemostat.alt_media_fraction,
            alt_media_fraction_post_dosing / (1 + 0.35 / 14),
        )


def test_chemostat_from_0_volume() -> None:
    experiment = "test_chemostat_from_0_volume"
    unit = get_unit_name()

    with start_dosing_automation(
        "chemostat",
        0.25,
        False,
        unit,
        experiment,
        volume=0.5,
        initial_vial_volume=0,
    ) as chemostat:
        pause(n=25)
        assert chemostat.media_throughput == 0.5
        assert chemostat.vial_volume == 0.5
        pause(n=25)
        assert chemostat.media_throughput == 1.0
        assert chemostat.vial_volume == 1.0


def test_execute_io_respects_dilutions_ratios() -> None:
    # https://forum.pioreactor.com/t/inconsistent-dosing-behavior-with-multiple-media/37/3

    unit = get_unit_name()
    experiment = "test_execute_io_respects_dilutions_ratios"

    class ChemostatAltMedia(DosingAutomationJob):
        automation_name = "_test_chemostat_alt_media"
        published_settings = {
            "volume": {"datatype": "float", "settable": True, "unit": "mL"},
            "duration": {"datatype": "float", "settable": True, "unit": "min"},
        }

        def __init__(self, volume: float, fraction_alt_media: float, **kwargs):
            super(ChemostatAltMedia, self).__init__(**kwargs)

            self.volume = float(volume)
            self.fraction_alt_media = float(fraction_alt_media)

        def execute(self) -> events.DilutionEvent:
            alt_media_ml = self.fraction_alt_media * self.volume
            media_ml = (1 - self.fraction_alt_media) * self.volume

            cycled = self.execute_io_action(
                alt_media_ml=alt_media_ml, media_ml=media_ml, waste_ml=self.volume
            )
            return events.DilutionEvent(data=cycled)

    with start_dosing_automation(
        "_test_chemostat_alt_media",
        2,
        False,
        unit,
        experiment,
        volume=2.0,
        initial_alt_media_fraction=0.5,
        fraction_alt_media=0.5,
    ) as automation_job:
        assert automation_job.alt_media_fraction == 0.5
        pause(n=100)
        assert automation_job.alt_media_fraction == 0.5

    # change fraction_alt_media to increase alt_media being added
    with start_dosing_automation(
        "_test_chemostat_alt_media", 2, False, unit, experiment, volume=2.0, fraction_alt_media=1.0
    ) as automation_job:
        assert automation_job.alt_media_fraction == 0.5
        pause(n=20)
        assert automation_job.alt_media_fraction > 0.5


def test_vial_volume_is_published() -> None:
    unit = get_unit_name()
    experiment = "test_vial_volume_is_published"

    with start_dosing_automation("chemostat", 2, False, unit, experiment, volume=2.0) as chemostat:
        assert chemostat.vial_volume == 14
        result = pubsub.subscribe(f"pioreactor/{unit}/{experiment}/dosing_automation/vial_volume")
        if result:
            assert float(result.payload) == 14


def test_vial_volume_calculator() -> None:
    # let's start from 0 volume, and start adding.
    vc = VialVolumeCalculator
    current_volume = 0.0

    # adding 6ml of media
    event = DosingEvent(
        volume_change=6,
        event="add_media",
        timestamp=default_datetime_for_pioreactor(0),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 6

    # try removing media, but this doesn't do anything since the level is too low.
    event = DosingEvent(
        volume_change=2,
        event="remove_waste",
        timestamp=default_datetime_for_pioreactor(1),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 6

    # add 6ml alt_media
    event = DosingEvent(
        volume_change=6,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(2),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 12

    # add 3ml alt_media
    event = DosingEvent(
        volume_change=3,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(3),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 15

    # try to remove 3ml, should not fall below minimum
    event = DosingEvent(
        volume_change=3,
        event="remove_waste",
        timestamp=default_datetime_for_pioreactor(4),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume != 12
    assert current_volume == 14  # TODO: this is equal to [bioreactor].max_volume_ml

    # add 2 more
    event = DosingEvent(
        volume_change=2,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(5),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 16

    # remove 1ml
    event = DosingEvent(
        volume_change=1,
        event="remove_waste",
        timestamp=default_datetime_for_pioreactor(6),
        source_of_event="test",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 15

    # remove 10ml manually
    event = DosingEvent(
        volume_change=10,
        event="remove_waste",
        timestamp=default_datetime_for_pioreactor(7),
        source_of_event="manually",
    )
    current_volume = vc.update(event, current_volume)
    assert current_volume == 5


def test_alt_media_calculator_from_0_volume() -> None:
    # let's start from 0, and start adding.
    ac = AltMediaFractionCalculator
    vc = VialVolumeCalculator

    current_volume = 0.0
    current_alt_media_fraction = 0.0  # this value doesn't matter, could be anything since volume = 0.

    # adding 6ml of media
    event = DosingEvent(
        volume_change=6,
        event="add_media",
        timestamp=default_datetime_for_pioreactor(0),
        source_of_event="test",
    )
    current_alt_media_fraction = ac.update(event, current_alt_media_fraction, current_volume)
    current_volume = vc.update(event, current_volume)
    assert current_alt_media_fraction == 0.0

    # removing media, but this doesn't do anything since it doesn't change the fraction
    event = DosingEvent(
        volume_change=2,
        event="remove_waste",
        timestamp=default_datetime_for_pioreactor(1),
        source_of_event="test",
    )
    current_alt_media_fraction = ac.update(event, current_alt_media_fraction, current_volume)
    current_volume = vc.update(event, current_volume)
    assert current_alt_media_fraction == 0.0

    # add 6ml alt_media
    event = DosingEvent(
        volume_change=6,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(2),
        source_of_event="test",
    )
    current_alt_media_fraction = ac.update(event, current_alt_media_fraction, current_volume)
    current_volume = vc.update(event, current_volume)
    assert current_alt_media_fraction == 0.5

    # add 3ml alt_media
    event = DosingEvent(
        volume_change=3,
        event="add_alt_media",
        timestamp=default_datetime_for_pioreactor(3),
        source_of_event="test",
    )
    current_alt_media_fraction = ac.update(event, current_alt_media_fraction, current_volume)
    current_volume = vc.update(event, current_volume)
    assert current_alt_media_fraction == 0.6


def test_adding_pumps_and_calling_them_from_execute_io_action() -> None:
    experiment = "test_adding_pumps_and_calling_them_from_execute_io_action"
    unit = get_unit_name()

    class ExternalAutomation(DosingAutomationJob):
        automation_name = "_test_external_automation"

        def add_salty_media_to_bioreactor(
            self, unit, experiment, ml, source_of_event, mqtt_client, logger
        ) -> float:
            logger.info(f"dosing {ml / 2}mL from salty")
            pause()
            return ml / 2

        def add_acid_media_to_bioreactor(
            self, unit, experiment, ml, source_of_event, mqtt_client, logger
        ) -> float:
            logger.info(f"dosing {ml}mL from acid")
            pause()
            return ml

        def execute(self):
            result = self.execute_io_action(waste_ml=1.0, salty_media_ml=0.75, acid_media_ml=0.25)
            assert result["waste_ml"] == 1.0
            assert result["salty_media_ml"] == 0.75 / 2
            assert result["acid_media_ml"] == 0.25
            return

    with start_dosing_automation(
        "_test_external_automation",
        5,
        False,
        unit,
        experiment,
    ):
        pause(40)


def test_execute_io_action_errors() -> None:
    experiment = "test_execute_io_action_errors"

    with Silent(
        unit=unit,
        experiment=experiment,
    ) as ca:
        with pytest.raises(ValueError):
            # missing _ml
            ca.execute_io_action(waste_ml=1.20, salty_media=1.0)

        with pytest.raises(ValueError):
            # waste < volume
            ca.execute_io_action(waste_ml=1.0, media_ml=2.0)

        with pytest.raises(AttributeError):
            # add_salty_media_to_bioreactor
            ca.execute_io_action(waste_ml=1.0, salty_media_ml=1.0)


def test_timeout_in_run() -> None:
    unit = get_unit_name()
    experiment = "test_timeout_in_run"

    with pubsub.collect_all_logs_of_level("DEBUG", unit, experiment) as bucket:
        with Silent(unit=unit, experiment=experiment, duration=5) as ca:
            ca.set_state(ca.SLEEPING)
            time.sleep(70)

        assert any("Timed out" in item["message"] for item in bucket)


def test_automation_will_pause_itself_if_pumping_goes_above_safety_threshold() -> None:
    experiment = "test_automation_will_pause_itself_if_pumping_goes_above_safety_threshold"

    with Chemostat(
        unit=unit,
        experiment=experiment,
        duration=0.05,
        volume=0.5,
        initial_vial_volume=17.95,
    ) as job:
        while job.state == "ready":
            pause()

        assert job.state == "sleeping"
        pause()

        # job is paused. Let's remove some liquid.
        job.remove_waste_from_bioreactor(job.unit, job.experiment, ml=5.0, source_of_event="manual")

        pause()
        assert job.vial_volume <= 17.95

        job.set_state("ready")
        assert job.state == "ready"

        pause()
        pause()
        pause()


def test_warning_is_logged_if_under_remove_waste() -> None:
    unit = get_unit_name()
    experiment = "test_warning_is_logged_if_under_remove_waste"

    class BadWasteRemoval(DosingAutomationJob):
        automation_name = "_test_bad_waste_removal"

        def remove_waste_from_bioreactor(self, unit, experiment, ml, source_of_event, mqtt_client, logger):
            return ml / 2

        def execute(self):
            self.execute_io_action(waste_ml=1.0, media_ml=1.0)
            return

    with pubsub.collect_all_logs_of_level("WARNING", unit, experiment) as bucket:
        pause(2)
        with BadWasteRemoval(unit=unit, experiment=experiment, duration=5):
            time.sleep(30)
        pause(2)

        assert len(bucket) >= 1


@pytest.mark.xfail
def test_a_failing_automation_cleans_duration_attr_in_mqtt_up() -> None:
    experiment = "test_a_failing_automation_cleans_itself_up"

    pubsub.publish(f"pioreactor/{get_unit_name()}/{experiment}/dosing_automation/duration", None, retain=True)

    class Failure(DosingAutomationJob):
        automation_name = "_test_failure"

        published_settings = {
            "duration": {"datatype": "float", "settable": True, "unit": "min"},
        }

        def __init__(self, volume: float | str, **kwargs) -> None:
            super().__init__(**kwargs)
            raise exc.CalibrationError("Media pump calibration must be performed first.")

    with pytest.raises(exc.CalibrationError):
        with start_dosing_automation("_test_failure", 60, False, get_unit_name(), experiment, volume=10):
            pass

    result = pubsub.subscribe(
        f"pioreactor/{get_unit_name()}/{experiment}/dosing_automation/duration", timeout=2
    )
    assert result is None
