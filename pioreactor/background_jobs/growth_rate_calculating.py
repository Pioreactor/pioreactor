# -*- coding: utf-8 -*-
"""
This job will combine the multiple PD sensors from od_reading and transforms them into
    i) a single growth rate,
    ii) "normalized" OD density,
    iii) other Kalman Filter outputs.


Topics published are:

    pioreactor/<unit>/<experiment>/growth_rate_calculating/growth_rate


with example payload

    {
        "growth_rate": 1.0,
        "timestamp": "2012-01-10T12:23:34.012313"
    },


And topic:

    pioreactor/<unit>/<experiment>/growth_rate_calculating/od_filtered

with payload

    {
        "od_filtered": 1.434,
        "timestamp": "2012-01-10T12:23:34.012313",
    }

"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from click import command
from click import option
from msgspec.json import decode

from pioreactor import exc
from pioreactor import structs
from pioreactor import types as pt
from pioreactor.actions.od_normalization import od_normalization
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.streaming_calculations import CultureGrowthEKF
from pioreactor.utils.timing import to_datetime
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env


class GrowthRateCalculator(BackgroundJob):

    published_settings = {
        "growth_rate": {
            "datatype": "GrowthRate",
            "settable": False,
            "unit": "h⁻¹",
            "persist": True,
        },
        "od_filtered": {"datatype": "ODFiltered", "settable": False, "persist": True},
    }

    def __init__(
        self,
        unit: str,
        experiment: str,
        ignore_cache: bool = False,
    ):

        super(GrowthRateCalculator, self).__init__(
            job_name="growth_rate_calculating", unit=unit, experiment=experiment
        )

        self.ignore_cache = ignore_cache
        self.time_of_previous_observation = datetime.utcnow()
        self.expected_dt = 1 / (
            60 * 60 * config.getfloat("od_config", "samples_per_second")
        )

    def on_init_to_ready(self) -> None:
        # this is here since the below is long running, and if kept in the init(), there is a large window where
        # two growth_rate_calculating jobs can be started.

        # Note that this function runs in the __post__init__, i.e. in the same frame as __init__, i.e.
        # when we initialize the class. Thus, we need to handle errors and cleanup resources gracefully.

        try:
            (
                self.initial_growth_rate,
                self.initial_od,
                self.od_normalization_factors,
                self.od_variances,
                self.od_blank,
                self.initial_acc,
            ) = self.get_precomputed_values()
        except Exception as e:
            self.clean_up()
            raise e

        self.ekf = self.initialize_extended_kalman_filter()
        self.start_passive_listeners()

    def on_sleeping_to_ready(self) -> None:
        # when the job sleeps, we expect a "big" jump in OD due to a few things:
        # 1. The delay between sleeping and resuming can causing a change in OD (as OD will keep changing)
        # 2. The user picks up the vial for inspection, places it back, but this causes an OD shift
        #    due to variation in the glass
        #
        # so to "fix" this, we will treat it like a dilution event, and modify the variances
        self.update_ekf_variance_after_event(minutes=0.5, factor=5e2)

    def initialize_extended_kalman_filter(self) -> CultureGrowthEKF:
        import numpy as np

        initial_state = np.array(
            [
                self.initial_od,
                self.initial_growth_rate,
                self.initial_acc,
            ]
        )

        initial_covariance = 1e-4 * np.eye(
            3
        )  # empirically selected - TODO: this should probably scale with `expected_dt`
        self.logger.debug(f"Initial covariance matrix:\n{str(initial_covariance)}")

        acc_std = config.getfloat("growth_rate_kalman", "acc_std")
        acc_process_variance = (acc_std * self.expected_dt) ** 2
        od_std = config.getfloat("growth_rate_kalman", "od_std")
        od_process_variance = (od_std * self.expected_dt) ** 2
        rate_std = config.getfloat("growth_rate_kalman", "rate_std")
        rate_process_variance = (rate_std * self.expected_dt) ** 2

        process_noise_covariance = np.zeros((3, 3))
        process_noise_covariance[0, 0] = od_process_variance
        process_noise_covariance[1, 1] = rate_process_variance
        process_noise_covariance[2, 2] = acc_process_variance
        self.logger.debug(
            f"Process noise covariance matrix:\n{str(process_noise_covariance)}"
        )

        observation_noise_covariance = self.create_obs_noise_covariance()
        self.logger.debug(
            f"Observation noise covariance matrix:\n{str(observation_noise_covariance)}"
        )

        angles = [
            angle
            for (_, angle) in config["od_config.photodiode_channel"].items()
            if angle in ["45", "90", "135", "180"]
        ]

        self.logger.debug(f"{angles=}")

        return CultureGrowthEKF(
            initial_state,
            initial_covariance,
            process_noise_covariance,
            observation_noise_covariance,
            angles,
        )

    def create_obs_noise_covariance(self):  # typing: ignore
        """
        Our sensor measurements have initial variance V, but in our KF, we scale them their
        initial mean, M. Hence the observed variance of the _normalized_ measurements is

        var(measurement / M) = V / M^2

        (there's also a blank to consider)


        However, we offer the variable ods_std to tweak this a bit.

        """
        import numpy as np

        try:

            scaling_obs_variances = np.array(
                [
                    self.od_variances[channel]
                    / (self.od_normalization_factors[channel] - self.od_blank[channel])
                    ** 2
                    for channel in self.od_normalization_factors
                ]
            )

            obs_variances = config.getfloat(
                "growth_rate_kalman", "obs_std"
            ) ** 2 * np.diag(scaling_obs_variances)
            return obs_variances
        except ZeroDivisionError:
            self.logger.debug(
                "Is there an OD Reading that is 0? Maybe there's a loose photodiode connection?",
                exc_info=True,
            )
            self.logger.error(
                "Is there an OD Reading that is 0? Maybe there's a loose photodiode connection?"
            )

            # we should clear the cache here...

            with local_persistant_storage("od_normalization_mean") as cache:
                del cache[self.experiment]

            with local_persistant_storage("od_normalization_variance") as cache:
                del cache[self.experiment]

            raise

    def get_precomputed_values(self) -> tuple:
        if self.ignore_cache:
            if not is_pio_job_running("od_reading"):
                self.logger.error("OD reading should be running. Stopping.")
                raise exc.JobRequiredError("OD reading should be running. Stopping.")

            self.logger.info(
                "Computing OD normalization metrics. This may take a few minutes"
            )
            od_normalization_factors, od_variances = od_normalization(
                unit=self.unit, experiment=self.experiment
            )
            self.logger.info("Completed OD normalization metrics.")
            initial_growth_rate = 0.0
            initial_od = 1.0
        else:
            od_normalization_factors = self.get_od_normalization_from_cache()
            od_variances = self.get_od_variances_from_cache()
            initial_growth_rate = self.get_growth_rate_from_cache()
            initial_od = self.get_previous_od_from_cache()

        initial_acc = 0
        od_blank = self.get_od_blank_from_cache()

        # what happens if od_blank is near / less than od_normalization_factors?
        # this means that the inoculant had near 0 impact on the turbidity => very dilute.
        # I think we should not use od_blank if so
        for channel in od_normalization_factors.keys():
            if od_normalization_factors[channel] * 0.95 < od_blank[channel]:
                self.logger.debug(
                    "Resetting od_blank because it is too close to current observations."
                )
                od_blank[channel] = od_normalization_factors[channel] * 0.95

        return (
            initial_growth_rate,
            initial_od,
            od_normalization_factors,
            od_variances,
            od_blank,
            initial_acc,
        )

    def get_od_blank_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistant_storage("od_blank") as cache:
            result = cache.get(self.experiment)

        if result:
            od_blanks = decode(result)
            self.logger.debug(f"{od_blanks=}")
            return od_blanks
        else:
            return defaultdict(lambda: 0)

    def get_growth_rate_from_cache(self) -> float:
        with local_persistant_storage("growth_rate") as cache:
            return float(cache.get(self.experiment, 0.0))

    def get_previous_od_from_cache(self) -> float:
        with local_persistant_storage("od_filtered") as cache:
            return float(cache.get(self.experiment, 1.0))

    def get_od_normalization_from_cache(self) -> dict[pt.PdChannel, float]:
        # we check if the broker has variance/mean stats
        with local_persistant_storage("od_normalization_mean") as cache:
            result = cache.get(self.experiment, None)

        if result is not None:
            return decode(result)
        else:
            self.logger.debug("od_normalization/mean not found in cache.")
            self.logger.info(
                "Calculating OD normalization metrics. This may take a few minutes"
            )
            means, _ = od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Finished calculating OD normalization metrics.")
            return means

    def get_od_variances_from_cache(self) -> dict[pt.PdChannel, float]:
        # we check if the broker has variance/mean stats
        with local_persistant_storage("od_normalization_variance") as cache:
            result = cache.get(self.experiment, None)

        if result:
            return decode(result)
        else:
            self.logger.debug("od_normalization/variance not found in cache.")
            self.logger.info(
                "Calculating OD normalization metrics. This may take a few minutes"
            )
            _, variances = od_normalization(unit=self.unit, experiment=self.experiment)
            self.logger.info("Finished calculating OD normalization metrics.")

            return variances

    def update_ekf_variance_after_event(self, minutes: float, factor: float) -> None:
        if is_testing_env():
            msg = subscribe(  # TODO: make this self.sub_client.subscribe?
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval",
                timeout=1.0,
            )
            if msg:
                interval = float(msg.payload)
            else:
                interval = 1
            self.ekf.scale_OD_variance_for_next_n_seconds(
                factor, minutes * (12 * interval)
            )
        else:
            self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * 60)

    def scale_raw_observations(
        self, observations: dict[pt.PdChannel, float]
    ) -> dict[pt.PdChannel, float]:
        def scale_and_shift(obs, shift, scale):
            return (obs - shift) / (scale - shift)

        v = {
            channel: scale_and_shift(
                raw_signal, self.od_blank[channel], self.od_normalization_factors[channel]
            )
            for channel, raw_signal in observations.items()
        }

        if any(v[a] < 0 for a in v):
            self.logger.warning(f"Negative normalized value(s) observed: {v}")
            self.logger.debug(
                f"od_normalization_factors: {self.od_normalization_factors}"
            )
            self.logger.debug(f"od_blank: {self.od_blank}")

        return v

    def update_state_from_observation(self, message) -> None:

        if self.state != self.READY:
            return

        payload = decode(message.payload, type=structs.ODReadings)
        observations = self.batched_raw_od_readings_to_dict(payload.od_raw)
        scaled_observations = self.scale_raw_observations(observations)

        if is_testing_env():
            # when running a mock script, we run at an accelerated rate, but want to mimic
            # production.
            dt = self.expected_dt
        else:
            # TODO this should use the internal timestamp reference

            time_of_current_observation = to_datetime(payload.timestamp)
            dt = (
                (
                    time_of_current_observation - self.time_of_previous_observation
                ).total_seconds()
                / 60
                / 60
            )  # delta time in hours

            if dt <= 0:
                self.logger.debug("Late arriving data...")
                return

            self.time_of_previous_observation = time_of_current_observation

        try:
            updated_state = self.ekf.update(list(scaled_observations.values()), dt)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(f"Updating Kalman Filter failed with {str(e)}")
            return
        else:

            # TODO: EKF values can be nans...

            latest_od_filtered, latest_growth_rate = float(updated_state[0]), float(
                updated_state[1]
            )

            self.growth_rate = structs.GrowthRate(
                growth_rate=latest_growth_rate,
                timestamp=payload.timestamp,
            )
            self.od_filtered = structs.ODFiltered(
                od_filtered=latest_od_filtered,
                timestamp=payload.timestamp,
            )

            with local_persistant_storage("growth_rate") as cache:
                cache[self.experiment] = str(latest_growth_rate)

            with local_persistant_storage("od_filtered") as cache:
                cache[self.experiment] = str(latest_od_filtered)

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/kalman_filter_outputs",
                {
                    "state": self.format_list(updated_state.tolist()),
                    "covariance_matrix": [
                        self.format_list(x) for x in self.ekf.covariance_.tolist()
                    ],
                    "timestamp": payload.timestamp,
                },
                qos=QOS.EXACTLY_ONCE,
            )

    @staticmethod
    def format_list(np_list: list[float]) -> list[str]:
        # we found that storing lists of floating point values as strings in the database
        # was consume a lot of storage on disk. So we format the values, without losing
        # much resolution, to reduce the storage impact.
        import numpy as np

        return [np.format_float_scientific(x, precision=2) for x in np_list]

    def response_to_dosing_event(self, message: pt.MQTTMessage) -> None:
        # here we can add custom logic to handle dosing events.

        # an improvement to this: the variance factor is proportional to the amount exchanged.
        self.update_ekf_variance_after_event(minutes=1, factor=2500)

    def start_passive_listeners(self) -> None:
        # process incoming data
        self.subscribe_and_callback(
            self.update_state_from_observation,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/od_raw_batched",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )
        self.subscribe_and_callback(
            self.response_to_dosing_event,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )

        # if the stirring is changed, this can effect the OD level, but not the
        # growth rate. Let's treat it the same how we treat a dosing event.
        # self.subscribe_and_callback(
        #     lambda m: self.update_ekf_variance_after_event(0.3, 5e2),
        #     f"pioreactor/{self.unit}/{self.experiment}/stirring/duty_cycle",
        #     qos=QOS.EXACTLY_ONCE,
        #     allow_retained=False,
        # )

    @staticmethod
    def batched_raw_od_readings_to_dict(raw_od_readings) -> dict[pt.PdChannel, float]:
        """
        Inputs looks like
        {
            0: {"voltage": 0.13, "angle": "135"},
            1: {"voltage": 0.03, "angle": "90"}
        }
        """
        return {
            channel: float(raw_od_readings[channel].voltage)
            for channel in sorted(raw_od_readings, reverse=True)
        }


@command(name="growth_rate_calculating")
@option("--ignore-cache", is_flag=True, help="Ignore the cached growth_rate value")
def click_growth_rate_calculating(ignore_cache):
    """
    Start calculating growth rate
    """
    import os

    os.nice(1)

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    calculator = GrowthRateCalculator(  # noqa: F841
        ignore_cache=ignore_cache, unit=unit, experiment=experiment
    )
    calculator.block_until_disconnected()
