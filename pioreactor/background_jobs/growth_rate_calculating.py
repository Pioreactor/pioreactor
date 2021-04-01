# -*- coding: utf-8 -*-
import json
import os
import signal
import logging

import click

from pioreactor.utils.streaming_calculations import ExtendedKalmanFilter
from pioreactor.utils import pio_jobs_running
from pioreactor.pubsub import subscribe, QOS

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.actions.od_normalization import od_normalization

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class GrowthRateCalculator(BackgroundJob):

    editable_settings = []

    def __init__(self, ignore_cache=False, unit=None, experiment=None):
        super(GrowthRateCalculator, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )

        self.ignore_cache = ignore_cache
        self.initial_growth_rate, self.od_normalization_factors, self.od_variances = (
            self.set_precomputed_values()
        )
        self.samples_per_minute = 60 * config.getfloat(
            "od_config.od_sampling", "samples_per_second"
        )
        self.rate_variance = config.getfloat("growth_rate_kalman", "rate_variance")
        self.od_variance = config.getfloat("growth_rate_kalman", "od_variance")
        self.dt = 1 / (self.samples_per_minute * 60)

        self.ekf, self.angles = self.initialize_extended_kalman_filter()
        self.start_passive_listeners()

    @property
    def state_(self):
        return self.ekf.state_

    def on_sleeping(self):
        # when the job sleeps, we expect a "big" jump in OD due to a few things:
        # 1. The delay between sleeping and resuming can causing a change in OD (as OD will keep changing)
        # 2. The user picks up the vial for inspection, places it back, but this causes an OD shift
        #    due to variation in the glass
        #
        # so to "fix" this, we will treat it like a dilution event, and modify the variances
        self.update_ekf_variance_after_event(minutes=0.5, factor=5e2)

    def initialize_extended_kalman_filter(self):
        import numpy as np

        latest_od = subscribe(f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched")
        angles_and_initial_points = self.scale_raw_observations(
            self.json_to_sorted_dict(latest_od.payload)
        )

        initial_state = np.array(
            [*angles_and_initial_points.values(), self.initial_growth_rate]
        )

        d = initial_state.shape[0]

        # empirically selected
        initial_covariance = 0.0001 * np.diag(initial_state.tolist()[:-1] + [0.00001])

        OD_process_covariance = self.create_OD_covariance(
            angles_and_initial_points.keys()
        )

        rate_process_variance = (self.rate_variance * self.dt) ** 2
        process_noise_covariance = np.block(
            [
                [OD_process_covariance, 0 * np.ones((d - 1, 1))],
                [0 * np.ones((1, d - 1)), rate_process_variance],
            ]
        )
        observation_noise_covariance = self.create_obs_noise_covariance(
            angles_and_initial_points.keys()
        )
        return (
            ExtendedKalmanFilter(
                initial_state,
                initial_covariance,
                process_noise_covariance,
                observation_noise_covariance,
                dt=self.dt,
            ),
            angles_and_initial_points.keys(),
        )

    def create_obs_noise_covariance(self, angles):
        import numpy as np

        # if a sensor has X times the variance of the other, we should encode this in the obs. covariance.
        obs_variances = np.array([self.od_variances[angle] for angle in angles])
        obs_variances = obs_variances / obs_variances.min()

        # add a fudge factor
        fudge = config.getfloat("growth_rate_kalman", "obs_variance")
        return fudge * (0.05 * self.dt) ** 2 * np.diag(obs_variances)

    def create_OD_covariance(self, angles):
        import numpy as np

        d = len(angles)
        variances = {
            "135": (self.od_variance * self.dt) ** 2,
            "90": (self.od_variance * self.dt) ** 2,
            "45": (self.od_variance * self.dt) ** 2,
        }

        OD_covariance = 0 * np.ones((d, d))
        for i, a in enumerate(angles):
            for k in variances:
                if a.startswith(k):
                    OD_covariance[i, i] = variances[k]
        return OD_covariance

    def set_precomputed_values(self):
        if self.ignore_cache:
            assert (
                "od_reading" in pio_jobs_running()
            ), "OD reading should be running. Stopping."
            # the below will populate od_norm and od_variance too
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")
            initial_growth_rate = 0
        else:
            initial_growth_rate = self.get_growth_rate_from_broker()

        od_normalization_factors = self.get_od_normalization_from_broker()
        od_variances = self.get_od_variances_from_broker()
        return initial_growth_rate, od_normalization_factors, od_variances

    def get_growth_rate_from_broker(self):
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return float(message.payload)
        else:
            return 0

    def get_od_normalization_from_broker(self):
        # we check if the broker has variance/mean stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/mean",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return self.json_to_sorted_dict(message.payload)
        else:
            self.logger.debug("od_normalization/mean not found in broker.")
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")
            return self.get_od_normalization_from_broker()

    def get_od_variances_from_broker(self):
        # we check if the broker has variance/mean stats
        message = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_normalization/variance",
            timeout=2,
            qos=QOS.EXACTLY_ONCE,
        )
        if message:
            return self.json_to_sorted_dict(message.payload)
        else:
            self.logger.debug("od_normalization/variance not found in broker.")
            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Computing OD normalization metrics completed.")

            return self.get_od_variances_from_broker()

    def update_ekf_variance_after_event(self, minutes, factor):
        self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * 60)

    def scale_raw_observations(self, observations):
        return {
            angle: observations[angle] / self.od_normalization_factors[angle]
            for angle in self.od_normalization_factors.keys()
        }

    def update_state_from_observation(self, message):
        if self.state != self.READY:
            return
        try:
            observations = self.json_to_sorted_dict(message.payload)
            scaled_observations = self.scale_raw_observations(observations)
            self.ekf.update(list(scaled_observations.values()))

            # TODO: EKF values can be nans...
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/growth_rate",
                self.state_[-1],
                retain=True,
            )

            for i, angle_label in enumerate(self.angles):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/od_filtered/{angle_label}",
                    self.state_[i],
                )

            self.logger.debug(f"state={self.ekf.state_}")
            self.logger.debug(f"covariance_=\n{self.ekf.covariance_}")
            self.logger.debug(
                f"process_noise_covariance=\n{self.ekf.process_noise_covariance}"
            )

            return

        except Exception as e:
            self.logger.error(f"failed with {str(e)}")
            raise e

    def response_to_dosing_event(self, message):
        # here we can add custom logic to handle dosing events.
        # for example, in continuous_cycle automation, we dont want to respond to
        # dosing events (because they are so small and so frequent)

        payload = json.loads(message.payload)
        if payload["source_of_event"] == "dosing_automation:ContinuousCycle":
            return

        # an improvement to this: the variance factor is proportional to the amount exchanged.
        self.update_ekf_variance_after_event(
            minutes=40 / 60,
            factor=150 / config.getfloat("growth_rate_kalman", "od_variance"),
        )

    def start_passive_listeners(self):
        # process incoming data
        self.subscribe_and_callback(
            self.update_state_from_observation,
            f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
            qos=QOS.EXACTLY_ONCE,
        )
        self.subscribe_and_callback(
            self.response_to_dosing_event,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
        )

        # if the stirring is changed, this can effect the OD level, but not the
        # growth rate. Let's treat it the same how we treat a dosing event.
        # self.subscribe_and_callback(
        #     lambda m: self.update_ekf_variance_after_event(0.3, 5e2),
        #     f"pioreactor/{self.unit}/{self.experiment}/stirring/duty_cycle",
        #     qos=QOS.EXACTLY_ONCE,
        #     allow_retained=False,
        # )
        # removed for now, because it was messing with the new dynamic stirring

    @staticmethod
    def json_to_sorted_dict(json_dict):
        d = json.loads(json_dict)
        return {
            k: float(d[k]) for k in sorted(d, reverse=True) if not k.startswith("180")
        }


def growth_rate_calculating_simulation(
    df,
    rate_variance=config.getfloat("growth_rate_kalman", "rate_variance"),
    od_variance=config.getfloat("growth_rate_kalman", "od_variance"),
    obs_variance_factor=100,
):
    """
    Since the KF is so finicky w.r.t. its parameters, it's useful for have a function that can "replay"
    a sequence of OD readings, and produce a new growth rate curve.

    df: DataFrame
        The dataframe from an export of od_readings_raw, subsetted to a single pioreactor, ex: `df = df[df['pioreactor_unit'] == 'pioreactor1']`
    """
    import pandas as pd
    import numpy as np

    samples_per_minute = (
        12
    )  # 60 * config.getfloat("od_config.od_sampling", "samples_per_second")
    dt = 1 / (samples_per_minute * 60)

    # pandas munging to get data in the correct format
    df["channel"] = df["channel"].astype(str)
    df["angle"] = df["angle"].astype(str)

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df = df.sort_index()
    df["angle_channel"] = df["angle"] + df["channel"]

    # compute the od normalization and od variance using the first 35 samples
    n_angles = df["angle_channel"].nunique()
    first_obs_for_med_and_variance = df.head(n_angles * 35)
    od_normalization_factors = (
        first_obs_for_med_and_variance.groupby("angle_channel", sort=True)["od_reading_v"]
        .mean()
        .to_dict()
    )
    od_obs_var = (
        first_obs_for_med_and_variance.groupby("angle_channel", sort=True)["od_reading_v"]
        .var()
        .to_dict()
    )

    def scale_raw_observations(observations):
        return {
            angle: observations[angle] / od_normalization_factors[angle]
            for angle in od_normalization_factors.keys()
        }

    def create_OD_covariance(angles):

        d = len(angles)
        variances = {
            "135": (od_variance * dt) ** 2,
            "90": (od_variance * dt) ** 2,
            "45": (od_variance * dt) ** 2,
        }

        OD_covariance = 0 * np.ones((d, d))
        for i, a in enumerate(angles):
            for k in variances:
                if a.startswith(k):
                    OD_covariance[i, i] = variances[k]
        return OD_covariance

    def create_obs_noise_covariance(angles):

        # if a sensor has X times the variance of the other, we should encode this in the obs. covariance.
        obs_variances = np.array([od_obs_var[angle] for angle in angles])
        obs_variances = obs_variances / obs_variances.min()

        # add a fudge factor
        fudge = obs_variance_factor
        return fudge * (0.05 * dt) ** 2 * np.diag(obs_variances)

    # get the latest observation
    angles_and_initial_points = scale_raw_observations(
        first_obs_for_med_and_variance.tail(n_angles)
        .groupby("angle_channel", sort=True)["od_reading_v"]
        .first()
        .to_dict()
    )

    initial_state = np.array([*angles_and_initial_points.values(), 0.0])

    d = initial_state.shape[0]

    # empirically selected
    initial_covariance = 0.00005 * np.diag(initial_state.tolist()[:-1] + [0.00001])

    OD_process_covariance = create_OD_covariance(angles_and_initial_points.keys())

    rate_process_variance = (rate_variance * dt) ** 2
    process_noise_covariance = np.block(
        [
            [OD_process_covariance, 0 * np.ones((d - 1, 1))],
            [0 * np.ones((1, d - 1)), rate_process_variance],
        ]
    )
    observation_noise_covariance = create_obs_noise_covariance(
        angles_and_initial_points.keys()
    )
    ekf = ExtendedKalmanFilter(
        initial_state,
        initial_covariance,
        process_noise_covariance.copy(),
        observation_noise_covariance.copy(),
        dt=dt,
    )

    grouped = (
        df[["angle_channel", "od_reading_v"]]
        .iloc[(n_angles * 35) :]
        .groupby(pd.Grouper(freq="5S"))
    )

    results = []
    index = []

    for ts, obs in grouped:
        obs = obs.set_index("angle_channel")["od_reading_v"].to_dict()
        scaled_observations = scale_raw_observations(obs)
        ekf.update(list(scaled_observations.values()))
        results.append(ekf.state_)

        index.append(ts)

    return pd.DataFrame(
        results, index=index, columns=[*angles_and_initial_points.keys(), "gr"]
    )


@click.command(name="growth_rate_calculating")
@click.option("--ignore-cache", is_flag=True, help="Ignore the cached growth_rate value")
def click_growth_rate_calculating(ignore_cache):
    """
    Start calculating growth rate
    """
    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    try:
        calculator = GrowthRateCalculator(  # noqa: F841
            ignore_cache=ignore_cache, unit=unit, experiment=experiment
        )
        while True:
            signal.pause()
    except Exception as e:
        logging.getLogger(JOB_NAME).error(f"{str(e)}")
        raise e
