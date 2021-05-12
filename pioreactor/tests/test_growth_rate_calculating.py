# -*- coding: utf-8 -*-
import json
import time
import numpy as np
from numpy.testing import assert_array_equal

from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.pubsub import publish
from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config

unit = get_unit_name()
experiment = get_latest_experiment_name()


def pause():
    # to avoid race conditions when updating state
    time.sleep(0.5)


def test_subscribing(monkeypatch):
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "90/0": 0.20944389172032837}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        1.0,
        retain=True,
    )
    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()
    assert calc.initial_growth_rate == 1.0

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "90/0": 0.20944389172032837}',
    )
    pause()

    assert calc.ekf is not None

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "90/0": 0.20944389172032837}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        '{"volume_change": "1.5", "event": "add_media", "source_of_event": "test"}',
    )
    publish(f"pioreactor/{unit}/{experiment}/stirring/duty_cycle", 45)
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 1.778586260567034, "90/0": 1.20944389172032837}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 1.778586260567034, "90/0": 1.20944389172032837}',
    )
    pause()

    assert calc.state_ is not None


def test_same_angles(monkeypatch):
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1, "135/1": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "135/1":1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "135/1": 0.20944389172032837, "90/0": 0.1}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "135/1": 0.20944389172032837, "90/0": 0.1}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.808586260567034, "135/1": 0.21944389172032837, "90/0": 0.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.808586260567034, "135/1": 0.21944389172032837, "90/0": 0.2}',
    )
    calc.set_state("disconnected")


def test_mis_shapen_data(monkeypatch):

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1,  "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "90/0": 1}',
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "90/0": 0.1}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "90/0": 0.1}',
    )
    pause()

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.808586260567034}',
    )
    pause()
    calc.set_state("disconnected")


def test_restart():
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1, "135/1": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "135/1": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.778586260567034, "135/1": 0.20944389172032837, "90/0": 0.1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 0.778586260567034, "135/1": 0.20944389172032837, "90/0": 0.1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "135/1": 1, "90/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    pause()
    calc1 = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 1.808586260567034, "135/1": 1.21944389172032837, "90/0": 1.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 2.808586260567034, "135/1": 2.21944389172032837, "90/0": 2.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 3.808586260567034, "135/1": 3.21944389172032837, "90/0": 3.2}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 4.808586260567034, "135/1": 4.21944389172032837, "90/0": 4.2}',
    )
    pause()

    assert calc1.state_[-1] != 0
    calc1.set_state("disconnected")

    calc2 = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()
    assert calc2.initial_growth_rate != 0
    calc2.set_state("disconnected")


def test_skip_180():
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1, "180/2": 1, "90/1": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1, "180/2": 1, "90/1": 1}',
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"180/2": 0.778586260567034, "135/0": 0.20944389172032837, "90/1": 0.1}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"180/2": 0.778586260567034, "135/0": 0.20944389172032837, "90/1": 0.1}',
    )
    pause()

    assert "180/2" not in calc.angles
    calc.set_state("disconnected")


def test_single_observation():
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        '{"135/0": 1}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        '{"135/0": 1}',
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.20944389172032837}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.20944389172032837}',
    )
    pause()

    assert True
    calc.set_state("disconnected")


def test_scaling_works():

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        json.dumps({"135/0": 0.5, "90/1": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps({"135/0": 1e-6, "90/1": 1e-4}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        "",
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.51, "90/1": 0.82}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.51, "90/1": 0.83}',
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.51, "90/1": 0.84}',
    )
    pause()
    assert calc.od_normalization_factors == {"90/1": 0.8, "135/0": 0.5}
    assert (
        (
            calc.ekf.observation_noise_covariance
            - 30 * np.array([[1e-4 / 0.8 ** 2, 0], [0, 1e-6 / 0.5 ** 2]])
        )
        < 1e-7
    ).all()
    calc.set_state("disconnected")


def test_shock_from_dosing_works():

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        json.dumps({"135/0": 0.5, "90/1": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps(
            {"135/0": 8.206_119_663_726_318e-07, "90/1": 8.206_119_663_726_318e-07}
        ),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        "",
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.51, "90/1": 0.82}',
    )
    pause()

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.52, "90/1": 0.81}',
    )
    pause()

    previous_covariance_matrix = calc.ekf.covariance_.copy()

    # trigger dosing events, which change the "regime"
    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        json.dumps(
            {"source_of_event": "algo", "event": "add_media", "volume_change": 1.0}
        ),
    )
    pause()

    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.50, "90/1": 0.78}',
    )
    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.45, "90/1": 0.75}',
    )
    pause()

    assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

    publish(
        f"pioreactor/{unit}/{experiment}/dosing_events",
        json.dumps(
            {"source_of_event": "algo", "event": "add_media", "volume_change": 1.0}
        ),
    )
    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.40, "90/1": 0.70}',
    )
    pause()

    time.sleep(55)
    assert calc.ekf._currently_scaling_od
    assert not np.array_equal(previous_covariance_matrix, calc.ekf.covariance_)

    time.sleep(5)
    pause()
    # should revert back
    assert not calc.ekf._currently_scaling_od
    assert_array_equal(calc.ekf.covariance_, previous_covariance_matrix)


def test_end_to_end():

    exp = "experiment"
    unit = "unit"
    interval = 0.1
    config["od_config.od_sampling"]["samples_per_second"] = "0.2"

    publish(
        f"pioreactor/{unit}/{exp}/growth_rate_calculating/growth_rate", None, retain=True
    )
    publish(f"pioreactor/{unit}/{exp}/od_normalization/mean", None, retain=True)
    publish(f"pioreactor/{unit}/{exp}/od_normalization/variance", None, retain=True)

    ODReader(
        channel_label_map={"A0": "135/0", "A1": "90/1"},
        sampling_rate=interval,
        unit=unit,
        experiment=exp,
        fake_data=True,
    )
    Stirrer(duty_cycle=50, unit=unit, experiment=exp)

    calc = GrowthRateCalculator(unit=unit, experiment=exp)

    time.sleep(35)
    assert calc.ekf.state_[-2] != 1.0


def test_od_blank_being_non_zero():

    publish(
        f"pioreactor/{unit}/{experiment}/od_blank/mean",
        json.dumps({"135/0": 0.25, "90/1": 0.4}),
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        json.dumps({"135/0": 0.5, "90/1": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps({"135/0": 1e-6, "90/1": 1e-4}),
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()

    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )
    pause()
    pause()
    assert calc.od_normalization_factors == {"90/1": 0.8, "135/0": 0.5}
    assert calc.od_blank == {"90/1": 0.4, "135/0": 0.25}
    results = calc.scale_raw_observations({"90/1": 1.0, "135/0": 0.6})
    assert abs(results["90/1"] - 1.5) < 0.00001
    assert abs(results["135/0"] - 1.4) < 0.00001

    calc.set_state("disconnected")


def test_od_blank_being_higher_than_observations():

    publish(
        f"pioreactor/{unit}/{experiment}/od_blank/mean",
        json.dumps({"135/0": 0.25, "90/1": 0.4}),
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        json.dumps({"135/0": 0.5, "90/1": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps({"135/0": 1e-6, "90/1": 1e-4}),
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()

    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )
    pause()
    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.1, "90/1": 0.1}',
        retain=True,
    )
    pause()
    pause()
    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.1, "90/1": 0.1}',
        retain=True,
    )
    pause()
    pause()
    pause()
    pause()
    calc.set_state("disconnected")


def test_od_blank_being_zero():

    publish(f"pioreactor/{unit}/{experiment}/od_blank/mean", None, retain=True)

    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/mean",
        json.dumps({"135/0": 0.5, "90/1": 0.8}),
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_normalization/variance",
        json.dumps({"135/0": 1e-6, "90/1": 1e-4}),
        retain=True,
    )

    publish(
        f"pioreactor/{unit}/{experiment}/growth_rate_calculating/growth_rate",
        None,
        retain=True,
    )
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )

    calc = GrowthRateCalculator(unit=unit, experiment=experiment)
    pause()

    pause()
    publish(
        f"pioreactor/{unit}/{experiment}/od_reading/od_raw_batched",
        '{"135/0": 0.5, "90/1": 0.8}',
        retain=True,
    )
    pause()
    pause()
    assert calc.od_normalization_factors == {"90/1": 0.8, "135/0": 0.5}
    assert calc.od_blank == {"90/1": 0.0, "135/0": 0.0}
    results = calc.scale_raw_observations({"90/1": 1.0, "135/0": 0.6})
    assert abs(results["90/1"] - 1.25) < 0.00001
    assert abs(results["135/0"] - 1.2) < 0.00001

    calc.set_state("disconnected")
