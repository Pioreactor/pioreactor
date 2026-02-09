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
from collections import defaultdict
from datetime import datetime
from statistics import mean
from threading import Event
from threading import Thread
from time import sleep
from typing import cast
from typing import Generator
from typing import Iterator

import click
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.actions.od_blank import od_statistics
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.od_reading import VALID_PD_ANGLES
from pioreactor.config import config
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.streaming import DosingObservationSource
from pioreactor.utils.streaming import merge_historical_streams
from pioreactor.utils.streaming import merge_live_streams
from pioreactor.utils.streaming import MqttDosingSource
from pioreactor.utils.streaming import MqttODFusedSource
from pioreactor.utils.streaming import MqttODSource
from pioreactor.utils.streaming import ODObservationSource
from pioreactor.utils.streaming_calculations import CultureGrowthEKF


def _should_use_fused_od(unit: pt.Unit) -> bool:
    try:
        model = whoami.get_pioreactor_model(unit)
    except Exception:
        return False

    if not model.model_name.endswith("_XR"):
        return False

    try:
        from pioreactor.estimators import load_active_estimator

        estimator = load_active_estimator(pt.OD_FUSED_DEVICE)
    except Exception:
        return False

    return isinstance(estimator, structs.ODFusionEstimator)


class GrowthRateCalculator(BackgroundJob):
    """
    Parameters
    -----------
    ignore_cache: bool
        ignore any cached calculated statistics from this experiment. Use if running a replay.
    """

    job_name = "growth_rate_calculating"
    published_settings = {
        "growth_rate": {
            "datatype": "GrowthRate",
            "settable": False,
            "unit": "h⁻¹",
        },
        "od_filtered": {"datatype": "ODFiltered", "settable": False},
        "kalman_filter_outputs": {
            "datatype": "KalmanFilterOutput",
            "settable": False,
        },
    }

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        ignore_cache: bool = False,
        use_fused_od: bool = False,
    ):
        super(GrowthRateCalculator, self).__init__(unit=unit, experiment=experiment)

        self.ignore_cache = ignore_cache
        self.use_fused_od = use_fused_od
        self.time_of_previous_observation: datetime | None = None
        self.expected_dt = 1 / (
            60 * 60 * config.getfloat("od_reading.config", "samples_per_second")
        )  # in hours

        # ekf parameters for when a dosing event occurs
        self._obs_since_last_dose: int | None = None
        self._obs_required_to_reset: int | None = None
        self._recent_dilution = False

        # runtime state initialized during processing
        self.ekf = cast(CultureGrowthEKF, None)
        self.od_normalization_factors: dict[pt.PdChannel, float] = {}
        self.od_variances: dict[pt.PdChannel, float] = {}
        self.od_blank: dict[pt.PdChannel, float] = {}
        self.growth_rate = cast(structs.GrowthRate, None)
        self.od_filtered = cast(structs.ODFiltered, None)
        self.kalman_filter_outputs = cast(structs.KalmanFilterOutput, None)
        self._initialization_complete = Event()

    def _initialize_extended_kalman_filter(
        self, od_std: float, rate_std: float, obs_std: float, od_iter: Iterator[structs.ODReadings]
    ) -> CultureGrowthEKF:
        import numpy as np

        self.logger.debug(f"{od_std=}, {rate_std=}, {obs_std=}")

        initial_nOD, initial_growth_rate = self._get_initial_values(od_iter)

        initial_state = np.array([initial_nOD, initial_growth_rate])
        self.logger.debug(f"Initial state: {repr(initial_state)}")

        initial_covariance = np.array(
            [
                [0.04**2, 0],
                [0, 0.01**2],
            ]
        )
        self.logger.debug(f"Initial covariance matrix:\n{repr(initial_covariance)}")
        od_process_variance = (od_std * self.expected_dt) ** 2
        rate_process_variance = (rate_std * self.expected_dt) ** 2
        process_noise_covariance = np.zeros((2, 2))
        process_noise_covariance[0, 0] = od_process_variance
        process_noise_covariance[1, 1] = rate_process_variance
        self.logger.debug(f"Process noise covariance matrix:\n{repr(process_noise_covariance)}")

        observation_noise_covariance = self._create_obs_noise_covariance(obs_std)
        self.logger.debug(f"Observation noise covariance matrix:\n{repr(observation_noise_covariance)}")

        if self.use_fused_od:
            angles = ["90"]
        else:
            angles = [
                angle
                for (_, angle) in config["od_config.photodiode_channel"].items()
                if angle in VALID_PD_ANGLES
            ]

        self.logger.debug(f"{angles=}")
        ekf_outlier_std_threshold = config.getfloat(
            "growth_rate_calculating.config",
            "ekf_outlier_std_threshold",
            fallback=3.0,
        )
        if ekf_outlier_std_threshold <= 2.0:
            raise ValueError(
                "outlier_std_threshold should not be less than 2.0 - that's eliminating too many data points."
            )

        self.logger.debug(f"{ekf_outlier_std_threshold=}")

        return CultureGrowthEKF(
            initial_state,
            initial_covariance,
            process_noise_covariance,
            observation_noise_covariance,
            angles,
            ekf_outlier_std_threshold,
        )

    def _create_obs_noise_covariance(self, obs_std):  # type: ignore
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
        except ZeroDivisionError:
            self.logger.debug(exc_info=True)
            # we should clear the cache here...

            with local_persistent_storage("od_normalization_mean") as cache:
                del cache[self.experiment]

            with local_persistent_storage("od_normalization_variance") as cache:
                del cache[self.experiment]

            raise ZeroDivisionError(
                "Is there an OD Reading that is 0? Maybe there's a loose photodiode connection?"
            )

    def _compute_and_cache_od_statistics(
        self, od_stream: ODObservationSource
    ) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
        # why sleep? Users sometimes spam jobs, and if stirring and gr start closely there can be a race to secure HALL_SENSOR. This gives stirring priority.
        sleep(0.5)
        if (
            config.getint("growth_rate_calculating.config", "samples_for_od_statistics", fallback=35)
            / config.getfloat("od_reading.config", "samples_per_second", fallback=0.2)
        ) >= 600:
            self.logger.warning(
                "Due to the low `samples_per_second`, and high `samples_for_od_statistics` needed to establish a baseline, initial growth rate and nOD may take over 10 minutes to show up."
            )
        means, variances = od_statistics(
            iter(od_stream),
            action_name="od_normalization",
            n_samples=config.getint(
                "growth_rate_calculating.config", "samples_for_od_statistics", fallback=35
            ),
            logger=self.logger,
            skip_stirring=od_stream.is_live,  # skip stirring if not using historical stream
        )
        self.logger.info("Completed OD normalization metrics.")

        if not self.ignore_cache:
            with local_persistent_storage("od_normalization_mean") as cache:
                if self.experiment not in cache:
                    cache[self.experiment] = dumps(means)

            with local_persistent_storage("od_normalization_variance") as cache:
                if self.experiment not in cache:
                    cache[self.experiment] = dumps(variances)

        return means, variances

    def _get_initial_values(self, od_iter: Iterator[structs.ODReadings]) -> tuple[float, float]:
        if self.ignore_cache:
            initial_growth_rate = 0.0
            initial_nOD = self._get_filtered_od_from_iterator(od_iter)
        else:
            initial_growth_rate = self._get_growth_rate_from_cache()
            initial_nOD = self._get_filtered_od_from_cache()
        return (initial_nOD, initial_growth_rate)

    def _get_precomputed_values(
        self, od_stream: ODObservationSource
    ) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
        if self.ignore_cache:
            od_normalization_factors, od_variances = self._compute_and_cache_od_statistics(od_stream)
        else:
            try:
                od_normalization_factors = self._get_od_normalization_from_cache()
                od_variances = self._get_od_variances_from_cache()
            except KeyError:
                self.logger.debug(
                    "OD normalization factors or variances not found in cache. Computing them now."
                )
                od_normalization_factors, od_variances = self._compute_and_cache_od_statistics(od_stream)

        if any(v == 0.0 for v in od_variances.values()):
            self.logger.error(
                "OD variance is zero - this suggests that the OD sensor is not working properly, or a calibration is wrong."
            )

        if not self.ignore_cache:
            od_blank = self._get_od_blank_from_cache()
        else:
            od_blank = defaultdict(lambda: 0.0)

        for channel in od_normalization_factors.keys():
            if od_normalization_factors[channel] * 0.90 < od_blank[channel]:
                self.logger.info("Resetting od_blank because it is too close to current observations.")
                od_blank[channel] = 0

        return (
            od_normalization_factors,
            od_variances,
            od_blank,
        )

    def _get_od_blank_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistent_storage("od_blank") as cache:
            result = cache.get(self.experiment)

        if result is not None:
            od_blanks = result
            return loads(od_blanks)
        else:
            return defaultdict(lambda: 0.0)

    def _get_growth_rate_from_cache(self) -> float:
        with local_persistent_storage("growth_rate") as cache:
            return cache.get(self.experiment, 0.0)

    def _get_filtered_od_from_cache(self) -> float:
        with local_persistent_storage("od_filtered") as cache:
            return cache.get(self.experiment, 1.0)

    def _get_filtered_od_from_iterator(self, od_iter: Iterator[structs.ODReadings]) -> float:
        scaled_od_readings = self.scale_raw_observations(next(od_iter))
        return mean(scaled_od_readings[channel] for channel in scaled_od_readings.keys())

    def _get_od_normalization_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistent_storage("od_normalization_mean") as cache:
            result = cache[self.experiment]
            return loads(result)

    def _get_od_variances_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistent_storage("od_normalization_variance") as cache:
            result = cache[self.experiment]
            return loads(result)

    @staticmethod
    def _scale_and_shift(obs: float, shift: float, scale: float) -> float:
        return (obs - shift) / (scale - shift)

    def scale_raw_observations(self, od_readings: structs.ODReadings) -> dict[pt.PdChannel, float]:
        scaled_signals = {
            channel: self._scale_and_shift(
                od_readings.ods[channel].od,
                self.od_blank[channel],
                self.od_normalization_factors[channel],
            )
            for channel in sorted(od_readings.ods, reverse=True)
        }

        if any(v <= 0.0 for v in scaled_signals.values()):
            raise ValueError(
                f"Non-positive normalized value(s) observed: {scaled_signals}. Likely optical signal received is less than the blank signal or OD reading is 0."
            )

        return scaled_signals

    def _update_state_from_observation(
        self, od_readings: structs.ODReadings
    ) -> tuple[structs.ODReadings, tuple[structs.GrowthRate, structs.ODFiltered, structs.KalmanFilterOutput]]:
        timestamp = od_readings.timestamp

        scaled_observations = self.scale_raw_observations(od_readings)

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
                    raise ValueError(
                        f"Late arriving data: {timestamp=}, {self.time_of_previous_observation=}"
                    )

            else:
                dt = 0.0

            self.time_of_previous_observation = timestamp

        updated_state_, covariance_ = self.ekf.update(
            list(scaled_observations.values()), dt, self._recent_dilution
        )
        latest_od_filtered, latest_growth_rate = float(updated_state_[0]), float(updated_state_[1])

        if self._obs_since_last_dose is not None and self._obs_required_to_reset is not None:
            self._obs_since_last_dose += 1

            if self._obs_since_last_dose >= self._obs_required_to_reset:
                self._obs_since_last_dose = None
                self._obs_required_to_reset = None
                self._recent_dilution = False

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
            covariance_matrix=covariance_.tolist(),
            timestamp=timestamp,
        )

        return od_readings, (growth_rate, od_filtered, kf_outputs)

    def _respond_to_dosing_event(self, dosing_event: structs.DosingEvent) -> None:
        self._obs_since_last_dose = 0
        self._obs_required_to_reset = 1
        self._recent_dilution = True

    def process_until_disconnected_or_exhausted_in_background(
        self,
        od_stream: ODObservationSource,
        dosing_stream: DosingObservationSource,
        wait_for_initialization: bool = False,
        timeout: float | None = 5.0,
    ) -> None:
        """
        This is function that will wrap process_until_disconnected_or_exhausted in a thread so the main thread can still do work (like publishing) - useful in tests.
        """

        def consume(od_stream: ODObservationSource, dosing_stream: DosingObservationSource) -> None:
            for _ in self.process_until_disconnected_or_exhausted(od_stream, dosing_stream):
                pass

        Thread(target=consume, args=(od_stream, dosing_stream), daemon=True).start()

        if wait_for_initialization:
            initialized = self._initialization_complete.wait(timeout)
            if not initialized:
                self.logger.debug("Timed out waiting for growth-rate initialization.")

    def process_until_disconnected_or_exhausted(
        self, od_stream: ODObservationSource, dosing_stream: DosingObservationSource
    ) -> Generator[tuple[structs.GrowthRate, structs.ODFiltered, structs.KalmanFilterOutput], None, None]:
        od_events_iter = self._initialize_state_and_get_od_iterator(od_stream, dosing_stream)

        if od_stream.is_live and dosing_stream.is_live:
            merged_streams = merge_live_streams(
                od_events_iter, dosing_stream, stop_event=self._blocking_event
            )
        elif not od_stream.is_live and not dosing_stream.is_live:
            merged_streams = merge_historical_streams(
                od_events_iter, dosing_stream, key=lambda t: t.timestamp
            )
        else:
            raise ValueError("Both streams must be live or both must be historical.")

        for event in merged_streams:
            if isinstance(event, structs.ODReadings):
                try:
                    _, (
                        self.growth_rate,
                        self.od_filtered,
                        self.kalman_filter_outputs,
                    ) = self._update_state_from_observation(event)
                except ValueError as e:
                    self.logger.error(f"Error processing OD readings: {e}", exc_info=True)
                    continue

                with local_persistent_storage("growth_rate") as cache:
                    cache[self.experiment] = self.growth_rate.growth_rate

                with local_persistent_storage("od_filtered") as cache:
                    cache[self.experiment] = self.od_filtered.od_filtered

                yield self.growth_rate, self.od_filtered, self.kalman_filter_outputs

            elif isinstance(event, structs.DosingEvent):
                self._respond_to_dosing_event(event)
            else:
                raise ValueError(f"Unexpected event type: {type(event)}. Expected ODReadings or DosingEvent.")

    def _initialize_state_and_get_od_iterator(
        self, od_stream: ODObservationSource, dosing_stream: DosingObservationSource
    ) -> Iterator[structs.ODReadings]:
        self._initialization_complete.clear()

        if od_stream.is_live and dosing_stream.is_live:
            od_stream.set_stop_event(self._blocking_event)
            dosing_stream.set_stop_event(self._blocking_event)

        (
            self.od_normalization_factors,
            self.od_variances,
            self.od_blank,
        ) = self._get_precomputed_values(od_stream)

        self.logger.debug(f"od_normalization_mean={self.od_normalization_factors}")
        self.logger.debug(f"od_normalization_variance={self.od_variances}")
        self.logger.debug(f"od_blank={dict(self.od_blank)}")

        od_events_iter = iter(od_stream)
        self.ekf = self._initialize_extended_kalman_filter(
            od_std=config.getfloat("growth_rate_kalman", "od_std"),
            rate_std=config.getfloat("growth_rate_kalman", "rate_std"),
            obs_std=config.getfloat("growth_rate_kalman", "obs_std"),
            od_iter=od_events_iter,
        )
        self._initialization_complete.set()
        return od_events_iter


@click.group(invoke_without_command=True, name="growth_rate_calculating")
@click.option("--ignore-cache", is_flag=True, help="Ignore the cached values (rerun)")
@click.pass_context
def click_growth_rate_calculating(ctx, ignore_cache):
    """
    Start calculating growth rate
    """
    if ctx.invoked_subcommand is None:
        unit = whoami.get_unit_name()
        experiment = whoami.get_assigned_experiment_name(unit)

        use_fused_od = _should_use_fused_od(unit)
        if use_fused_od:
            od_stream = MqttODFusedSource(unit=unit, experiment=experiment, skip_first=5)
        else:
            od_stream = MqttODSource(unit=unit, experiment=experiment, skip_first=5)
        dosing_stream = MqttDosingSource(unit=unit, experiment=experiment)

        with GrowthRateCalculator(
            unit=unit,
            experiment=experiment,
            ignore_cache=ignore_cache,
            use_fused_od=use_fused_od,
        ) as job:
            for _ in job.process_until_disconnected_or_exhausted(
                od_stream=od_stream, dosing_stream=dosing_stream
            ):
                continue


@click_growth_rate_calculating.command(name="clear_cache")
def click_clear_cache() -> None:
    unit = whoami.get_unit_name()
    experiment = whoami.get_assigned_experiment_name(unit)

    with local_persistent_storage("od_filtered") as cache:
        cache.pop(experiment)
    with local_persistent_storage("growth_rate") as cache:
        cache.pop(experiment)
    with local_persistent_storage("od_normalization_mean") as cache:
        cache.pop(experiment)
    with local_persistent_storage("od_normalization_variance") as cache:
        cache.pop(experiment)
