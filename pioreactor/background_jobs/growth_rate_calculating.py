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


Incoming OD readings are normalized by the value, called the reference OD, in the cache od_normalization_mean, indexed by the experiment name. You can change
the reference OD by supplying a value to this cache first. See example https://gist.github.com/CamDavidsonPilon/e5f2b0d03bf6eefdbf43f6653b8149ba
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from json import dumps
from json import loads
from statistics import mean
from typing import Generator

from click import command
from click import option
from msgspec.json import decode

from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.actions.od_blank import od_statistics
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.od_reading import VALID_PD_ANGLES
from pioreactor.config import config
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.streaming_calculations import CultureGrowthEKF


class GrowthRateCalculator(BackgroundJob):
    """
    Parameters
    -----------
    ignore_cache: bool
        ignore any cached calculated statistics from this experiment.
    from_mqtt: bool
        listen for data from MQTT to respond to.

    """

    job_name = "growth_rate_calculating"
    published_settings = {
        "growth_rate": {
            "datatype": "GrowthRate",
            "settable": False,
            "unit": "h⁻¹",
            "persist": True,  # why persist?
        },
        "od_filtered": {"datatype": "ODFiltered", "settable": False, "persist": True},
        "kalman_filter_outputs": {
            "datatype": "KalmanFilterOutput",
            "settable": False,
            "persist": False,
        },
    }

    def __init__(
        self,
        unit: str,
        experiment: str,
        ignore_cache: bool = False,
        from_mqtt=True,
    ):
        super(GrowthRateCalculator, self).__init__(unit=unit, experiment=experiment)

        self.from_mqtt = from_mqtt
        self.ignore_cache = ignore_cache
        self.time_of_previous_observation: datetime | None = None
        self.expected_dt = 1 / (60 * 60 * config.getfloat("od_config", "samples_per_second"))

    def on_init_to_ready(self) -> None:
        # this is here since the below is long running, and if kept in the init(), there is a large window where
        # two growth_rate_calculating jobs can be started.

        # Note that this function runs in the __post__init__, i.e. in the same frame as __init__, i.e.
        # when we initialize the class. Thus, we need to handle errors and cleanup resources gracefully.

        try:
            (
                self.od_normalization_factors,
                self.od_variances,
                self.od_blank,
            ) = self.get_precomputed_values()
            (
                self.initial_nOD,
                self.initial_growth_rate,
                self.initial_acc,
            ) = self.get_initial_values()
        except Exception as e:
            # something happened - abort
            self.logger.debug("Aborting early`.", exc_info=True)
            self.clean_up()
            raise e

        self.logger.debug(f"od_blank={dict(self.od_blank)}")
        self.logger.debug(f"od_normalization_mean={self.od_normalization_factors}")
        self.logger.debug(f"od_normalization_variance={self.od_variances}")
        self.ekf = self.initialize_extended_kalman_filter(
            acc_std=config.getfloat("growth_rate_kalman", "acc_std"),
            od_std=config.getfloat("growth_rate_kalman", "od_std"),
            rate_std=config.getfloat("growth_rate_kalman", "rate_std"),
            obs_std=config.getfloat("growth_rate_kalman", "obs_std"),
        )

        if self.from_mqtt:
            self.start_passive_listeners()

    def initialize_extended_kalman_filter(
        self, acc_std: float, od_std: float, rate_std: float, obs_std: float
    ) -> CultureGrowthEKF:
        import numpy as np

        initial_state = np.array(
            [
                self.initial_nOD,
                self.initial_growth_rate,
                self.initial_acc,
            ]
        )
        self.logger.debug(f"Initial state: {repr(initial_state)}")

        initial_covariance = 1e-4 * np.eye(
            3
        )  # empirically selected - TODO: this should probably scale with `expected_dt`
        self.logger.debug(f"Initial covariance matrix:\n{repr(initial_covariance)}")

        acc_process_variance = (acc_std * self.expected_dt) ** 2
        od_process_variance = (od_std * self.expected_dt) ** 2
        rate_process_variance = (rate_std * self.expected_dt) ** 2

        process_noise_covariance = np.zeros((3, 3))
        process_noise_covariance[0, 0] = od_process_variance
        process_noise_covariance[1, 1] = rate_process_variance
        process_noise_covariance[2, 2] = acc_process_variance
        self.logger.debug(f"Process noise covariance matrix:\n{repr(process_noise_covariance)}")

        observation_noise_covariance = self.create_obs_noise_covariance(obs_std)
        self.logger.debug(
            f"Observation noise covariance matrix:\n{repr(observation_noise_covariance)}"
        )

        angles = [
            angle
            for (_, angle) in config["od_config.photodiode_channel"].items()
            if angle in VALID_PD_ANGLES
        ]

        self.logger.debug(f"{angles=}")

        return CultureGrowthEKF(
            initial_state,
            initial_covariance,
            process_noise_covariance,
            observation_noise_covariance,
            angles,
        )

    def create_obs_noise_covariance(self, obs_std):  # typing: ignore
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
                    / (self.od_normalization_factors[channel] - self.od_blank[channel]) ** 2
                    for channel in self.od_normalization_factors
                ]
            )

            obs_variances = obs_std**2 * np.diag(scaling_obs_variances)
            return obs_variances
        except ZeroDivisionError as e:
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

            raise e

    def _compute_and_cache_od_statistics(
        self,
    ) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
        means, variances = od_statistics(
            self._yield_od_readings_from_mqtt(),
            action_name="od_normalization",
            n_samples=35,
            unit=self.unit,
            experiment=self.experiment,
            logger=self.logger,
        )
        self.logger.info("Completed OD normalization metrics.")

        with local_persistant_storage("od_normalization_mean") as cache:
            if self.experiment not in cache:
                cache[self.experiment] = dumps(means)

        with local_persistant_storage("od_normalization_variance") as cache:
            if self.experiment not in cache:
                cache[self.experiment] = dumps(variances)

        return means, variances

    def get_initial_values(self) -> tuple[float, float, float]:
        if self.ignore_cache:
            initial_growth_rate = 0.0
            initial_nOD = 1.0
        else:
            initial_growth_rate = self.get_growth_rate_from_cache()
            initial_nOD = self.get_filtered_od_from_cache_or_computed()
        initial_acc = 0.0
        return (initial_nOD, initial_growth_rate, initial_acc)

    def get_precomputed_values(
        self,
    ) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
        if self.ignore_cache:
            od_normalization_factors, od_variances = self._compute_and_cache_od_statistics()
        else:
            od_normalization_factors = self.get_od_normalization_from_cache()
            od_variances = self.get_od_variances_from_cache()

        od_blank = self.get_od_blank_from_cache()

        # what happens if od_blank is near / less than od_normalization_factors?
        # this means that the inoculant had near 0 impact on the turbidity => very dilute.
        # I think we should not use od_blank if so
        for channel in od_normalization_factors.keys():
            if od_normalization_factors[channel] * 0.90 < od_blank[channel]:
                self.logger.debug(
                    "Resetting od_blank because it is too close to current observations."
                )
                od_blank[channel] = 0

        return (
            od_normalization_factors,
            od_variances,
            od_blank,
        )

    def get_od_blank_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistant_storage("od_blank") as cache:
            result = cache.get(self.experiment)

        if result is not None:
            od_blanks = result
            return loads(od_blanks)
        else:
            return defaultdict(lambda: 0.0)

    def get_growth_rate_from_cache(self) -> float:
        with local_persistant_storage("growth_rate") as cache:
            return cache.get(self.experiment, 0.0)

    def get_filtered_od_from_cache_or_computed(self) -> float:
        with local_persistant_storage("od_filtered") as cache:
            if self.experiment in cache:
                return cache[self.experiment]

        # we compute a good initial guess
        # typically this should be near 1.0, but if the od_normalization_factors are very different (i.e. provided elsewhere.),
        # then this could be a different value.
        msg = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
            allow_retained=True,
            timeout=10,
        )

        if msg is None:
            return 1.0  # default?

        od_readings = decode(msg.payload, type=structs.ODReadings)
        scaled_ods = self.scale_raw_observations(
            self._batched_raw_od_readings_to_dict(od_readings.ods)
        )

        return mean(scaled_ods.values())

    def get_od_normalization_from_cache(self) -> dict[pt.PdChannel, float]:
        # we check if we've computed mean stats
        with local_persistant_storage("od_normalization_mean") as cache:
            result = cache.get(self.experiment, None)
            if result is not None:
                return loads(result)

        self.logger.debug("od_normalization/mean not found in cache.")
        means, _ = self._compute_and_cache_od_statistics()

        return means

    def get_od_variances_from_cache(self) -> dict[pt.PdChannel, float]:
        # we check if we've computed variance stats
        with local_persistant_storage("od_normalization_variance") as cache:
            result = cache.get(self.experiment, None)
            if result:
                return loads(result)

        self.logger.debug("od_normalization/mean not found in cache.")
        _, variances = self._compute_and_cache_od_statistics()

        return variances

    def update_ekf_variance_after_event(self, minutes: float, factor: float) -> None:
        if whoami.is_testing_env():
            msg = subscribe(  # needs to be pubsub.subscribe (ie not sub_client.subscribe) since this is called in a callback
                f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval",
                timeout=1.0,
            )
            if msg:
                interval = float(msg.payload)
            else:
                interval = 5
            self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * (12 * interval))
        else:
            self.ekf.scale_OD_variance_for_next_n_seconds(factor, minutes * 60)

    @staticmethod
    def _scale_and_shift(obs, shift, scale) -> float:
        return (obs - shift) / (scale - shift)

    def scale_raw_observations(
        self, observations: dict[pt.PdChannel, float]
    ) -> dict[pt.PdChannel, float]:
        scaled_signals = {
            channel: self._scale_and_shift(
                raw_signal, self.od_blank[channel], self.od_normalization_factors[channel]
            )
            for channel, raw_signal in observations.items()
        }

        if any(v <= 0.0 for v in scaled_signals.values()):
            self.logger.warning(f"Negative normalized value(s) observed: {scaled_signals}")
            self.logger.debug(f"od_normalization_factors: {self.od_normalization_factors}")
            self.logger.debug(f"od_blank: {self.od_blank}")

        return scaled_signals

    def respond_to_od_readings_from_mqtt(self, message: pt.MQTTMessage) -> None:
        if self.state != self.READY:
            return

        od_readings = decode(message.payload, type=structs.ODReadings)

        self.update_state_from_observation(od_readings)

        return

    def update_state_from_observation(
        self, od_readings: structs.ODReadings
    ) -> tuple[structs.GrowthRate, structs.ODFiltered, structs.KalmanFilterOutput]:
        """
        this is like _update_state_from_observation, but also updates attributes, caches, mqtt
        """
        (
            self.growth_rate,
            self.od_filtered,
            self.kalman_filter_outputs,
        ) = self._update_state_from_observation(od_readings)

        # save to cache
        with local_persistant_storage("growth_rate") as cache:
            cache[self.experiment] = self.growth_rate.growth_rate

        with local_persistant_storage("od_filtered") as cache:
            cache[self.experiment] = self.od_filtered.od_filtered

        return self.growth_rate, self.od_filtered, self.kalman_filter_outputs

    def _update_state_from_observation(
        self, od_readings: structs.ODReadings
    ) -> tuple[structs.GrowthRate, structs.ODFiltered, structs.KalmanFilterOutput]:
        timestamp = od_readings.timestamp
        scaled_observations = self.scale_raw_observations(
            self._batched_raw_od_readings_to_dict(od_readings.ods)
        )

        if whoami.is_testing_env():
            # when running a mock script, we run at an accelerated rate, but want to mimic
            # production.
            dt = self.expected_dt
        else:
            if self.time_of_previous_observation is not None:
                dt = (
                    (timestamp - self.time_of_previous_observation).total_seconds() / 60 / 60
                )  # delta time in hours

                if dt < 0:
                    self.logger.debug(
                        f"Late arriving data: {timestamp=}, {self.time_of_previous_observation=}"
                    )
                    return self.growth_rate, self.od_filtered, self.kalman_filter_outputs

            else:
                dt = 0.0

            self.time_of_previous_observation = timestamp

        try:
            updated_state = self.ekf.update(list(scaled_observations.values()), dt)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(f"Updating Kalman Filter failed with {str(e)}")
            return self.growth_rate, self.od_filtered, self.kalman_filter_outputs
        else:
            # TODO: EKF values can be nans...

            latest_od_filtered, latest_growth_rate = float(updated_state[0]), float(
                updated_state[1]
            )

            growth_rate = structs.GrowthRate(
                growth_rate=latest_growth_rate,
                timestamp=timestamp,
            )
            od_filtered = structs.ODFiltered(
                od_filtered=latest_od_filtered,
                timestamp=timestamp,
            )

            kf_outputs = structs.KalmanFilterOutput(
                state=self.ekf.state_.tolist(),
                covariance_matrix=self.ekf.covariance_.tolist(),
                timestamp=timestamp,
            )

            return growth_rate, od_filtered, kf_outputs

    def respond_to_dosing_event_from_mqtt(self, message: pt.MQTTMessage) -> None:
        dosing_event = decode(message.payload, type=structs.DosingEvent)
        return self.respond_to_dosing_event(dosing_event)

    def respond_to_dosing_event(self, dosing_event: structs.DosingEvent) -> None:
        # here we can add custom logic to handle dosing events.
        # an improvement to this: the variance factor is proportional to the amount exchanged.
        if dosing_event.event != "remove_waste":
            self.update_ekf_variance_after_event(
                minutes=config.getfloat(
                    "growth_rate_calculating.config",
                    "ekf_variance_shift_post_dosing_minutes",
                    fallback=0.40,
                ),
                factor=config.getfloat(
                    "growth_rate_calculating.config",
                    "ekf_variance_shift_post_dosing_factor",
                    fallback=2500,
                ),
            )

    def start_passive_listeners(self) -> None:
        # process incoming data
        self.subscribe_and_callback(
            self.respond_to_od_readings_from_mqtt,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )
        self.subscribe_and_callback(
            self.respond_to_dosing_event_from_mqtt,
            f"pioreactor/{self.unit}/{self.experiment}/dosing_events",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )

    @staticmethod
    def _batched_raw_od_readings_to_dict(
        raw_od_readings: dict[pt.PdChannel, structs.ODReading]
    ) -> dict[pt.PdChannel, float]:
        """
        Extract the od floats from ODReading but keep the same keys
        """
        return {
            channel: raw_od_readings[channel].od
            for channel in sorted(raw_od_readings, reverse=True)
        }

    def _yield_od_readings_from_mqtt(self) -> Generator[structs.ODReadings, None, None]:
        counter = 0

        while True:
            msg = subscribe(
                f"pioreactor/{self.unit}/{self.experiment}/od_reading/ods",
                allow_retained=False,
                timeout=10,
            )

            if self.state not in (self.READY, self.INIT):
                raise StopIteration("Ending early.")

            if msg is None:
                continue

            counter += 1
            if counter <= 3:
                continue  # skip the first few values. If users turn on growth_rate, THEN od_reading, we should ignore the noisiest part of od_reading.

            yield decode(msg.payload, type=structs.ODReadings)


@command(name="growth_rate_calculating")
@option("--ignore-cache", is_flag=True, help="Ignore the cached values (rerun)")
def click_growth_rate_calculating(ignore_cache):
    """
    Start calculating growth rate
    """
    import os

    os.nice(1)

    calculator = GrowthRateCalculator(  # noqa: F841
        ignore_cache=ignore_cache,
        unit=whoami.get_unit_name(),
        experiment=whoami.get_latest_experiment_name(),
    )
    calculator.block_until_disconnected()
