# -*- coding: utf-8 -*-
import time
from datetime import datetime
from datetime import timezone
from typing import Callable

from msgspec.json import encode
from pioreactor import structs
from pioreactor.automations.dosing.turbidostat import EventBasedTurbidostat
from pioreactor.utils import get_running_pio_job_id
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name


unit = get_unit_name()


def wait_for(predicate: Callable[[], bool], timeout: float = 5.0, check_interval: float = 0.01) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if predicate():
                return True
        except Exception:
            pass
        time.sleep(check_interval)
    return False


class DummyMessage:
    def __init__(self, payload: bytes, retain: bool = False, topic: str = "") -> None:
        self.payload = payload
        self.retain = retain
        self.topic = topic


def setup_function() -> None:
    job_id = get_running_pio_job_id("dosing_automation")
    if job_id is not None:
        with JobManager() as jm:
            jm.set_not_running(job_id)

    cal = structs.SimplePeristalticPumpCalibration(
        calibration_name="setup_function",
        curve_data_=structs.PolyFitCoefficients(coefficients=[1.0, 0.0]),
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


def test_event_based_turbidostat_targeting_nod() -> None:
    experiment = "test_event_based_turbidostat_targeting_nod"
    target_nod = 1.0
    queued_runs = {"count": 0}

    def queue_run() -> None:
        queued_runs["count"] += 1

    with EventBasedTurbidostat(
        target_normalized_od=target_nod,
        exchange_volume_ml=0.1,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert wait_for(lambda: algo.state == algo.READY, timeout=5.0)
        algo._queue_event_based_run = queue_run  # type: ignore[method-assign]

        algo._set_normalized_od(
            DummyMessage(
                payload=encode(structs.ODFiltered(od_filtered=1.05, timestamp=current_utc_datetime()))
            )
        )
        assert queued_runs["count"] == 1

        algo._set_ods(
            DummyMessage(
                payload=encode(
                    structs.ODReadings(
                        timestamp=current_utc_datetime(),
                        ods={
                            "2": structs.RawODReading(
                                ir_led_intensity=80.0,
                                timestamp=current_utc_datetime(),
                                angle="45",
                                od=0.5,
                                channel="2",
                            )
                        },
                    )
                )
            )
        )
        assert queued_runs["count"] == 1


def test_event_based_turbidostat_targeting_od() -> None:
    experiment = "test_event_based_turbidostat_targeting_od"
    target_od = 0.1
    queued_runs = {"count": 0}

    def queue_run() -> None:
        queued_runs["count"] += 1

    with EventBasedTurbidostat(
        target_od=target_od,
        exchange_volume_ml=0.1,
        unit=unit,
        experiment=experiment,
    ) as algo:
        assert wait_for(lambda: algo.state == algo.READY, timeout=5.0)
        algo._queue_event_based_run = queue_run  # type: ignore[method-assign]

        algo._set_ods(
            DummyMessage(
                payload=encode(
                    structs.ODReadings(
                        timestamp=current_utc_datetime(),
                        ods={
                            "2": structs.RawODReading(
                                ir_led_intensity=80.0,
                                timestamp=current_utc_datetime(),
                                angle="45",
                                od=0.5,
                                channel="2",
                            )
                        },
                    )
                )
            )
        )
        assert queued_runs["count"] == 1

        algo._set_normalized_od(
            DummyMessage(
                payload=encode(structs.ODFiltered(od_filtered=1.2, timestamp=current_utc_datetime()))
            )
        )
        assert queued_runs["count"] == 1
