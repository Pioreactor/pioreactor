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
from itertools import chain
from math import exp
from math import log
from statistics import mean
from statistics import median
from threading import Event
from threading import Thread
from typing import Any
from typing import cast
from typing import Generator
from typing import Iterator

import click
from msgspec.json import encode as dumps
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.streaming import DosingObservationSource
from pioreactor.utils.streaming import merge_live_streams
from pioreactor.utils.streaming import MqttDosingSource
from pioreactor.utils.streaming import MqttODFusedSource
from pioreactor.utils.streaming import MqttODSource
from pioreactor.utils.streaming import ODObservationSource

try:
    from grpredict import CultureGrowthEKF as CultureGrowthEKF
except ImportError:
    pass


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
    ):
        super(GrowthRateCalculator, self).__init__(unit=unit, experiment=experiment)

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
        self.growth_rate = cast(structs.GrowthRate, None)
        self.od_filtered = cast(structs.ODFiltered, None)
        self.kalman_filter_outputs = cast(structs.KalmanFilterOutput, None)
        self._initialization_complete = Event()

    def _initialize_extended_kalman_filter(
        self, warmup_observations: list[dict[pt.PdChannel, float]]
    ) -> CultureGrowthEKF:
        import numpy as np

        self.logger.info("Initializing growth-rate filter from warmup observations.")
        observation_noise_covariance = self._create_obs_noise_covariance_from_warmup_observations(
            warmup_observations
        )
        self.logger.debug(f"Observation noise covariance matrix:\n{repr(observation_noise_covariance)}")
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

        initial_nOD, initial_growth_rate = self._get_initial_values_from_warmup_observations(
            warmup_observations
        )
        initial_state = np.array([log(max(initial_nOD, 1e-9)), initial_growth_rate, 0.0])
        self.logger.debug(f"Initial state: {repr(initial_state)}")
        initial_covariance = self._create_initial_covariance(
            warmup_observations=warmup_observations,
            observation_noise_covariance=observation_noise_covariance,
        )
        self.logger.debug(f"Initial covariance matrix:\n{repr(initial_covariance)}")
        process_noise_covariance = self._create_process_noise_covariance_for_hidden_state()
        self.logger.debug(f"Process noise covariance matrix:\n{repr(process_noise_covariance)}")
        return CultureGrowthEKF(
            initial_state,
            initial_covariance,
            process_noise_covariance,
            observation_noise_covariance,
            ekf_outlier_std_threshold,
        )

    def _create_initial_covariance(
        self,
        warmup_observations: list[dict[pt.PdChannel, float]],
        observation_noise_covariance: Any,
    ) -> Any:
        import numpy as np

        fused_observations = self._fuse_warmup_observations(warmup_observations)
        log_warmup = np.log(np.maximum(np.asarray(fused_observations, dtype=float), 1e-9))
        sigma_log_od0 = max(
            0.05,
            2.0 * self._robust_std(log_warmup),
            float(np.mean(np.diag(observation_noise_covariance))) ** 0.5,
        )

        sigma_growth_rate0 = 0.03
        sigma_growth_rate_drift0 = 0.05

        return np.diag(
            [
                sigma_log_od0**2,
                sigma_growth_rate0**2,
                sigma_growth_rate_drift0**2,
            ]
        )

    def _create_process_noise_covariance_for_hidden_state(self) -> Any:
        import numpy as np

        reference_dt_hours = 5.0 / 60.0 / 60.0
        scale = max(self.expected_dt / reference_dt_hours, 0.25)
        return np.diag([1e-8 * scale, 5e-8 * scale, 5e-6 * scale])

    def _create_obs_noise_covariance_from_warmup_observations(
        self, warmup_observations: list[dict[pt.PdChannel, float]]
    ) -> Any:
        """
        Estimate sensor noise from a warmup window of already-normalized observations.
        """
        import numpy as np

        if len(warmup_observations) < 2:
            return np.diag([1e-3 for _ in self.od_normalization_factors])

        observation_matrix = np.asarray(
            [
                [warmup_observation[channel] for channel in self.od_normalization_factors]
                for warmup_observation in warmup_observations
            ],
            dtype=float,
        )
        time_hours = np.arange(observation_matrix.shape[0], dtype=float) * float(self.expected_dt)
        design = np.column_stack([np.ones(observation_matrix.shape[0], dtype=float), time_hours])

        log_residual_variances: list[float] = []
        for sensor_index in range(observation_matrix.shape[1]):
            log_warmup = np.log(np.maximum(observation_matrix[:, sensor_index], 1e-9))
            coefficients, _, _, _ = np.linalg.lstsq(design, log_warmup, rcond=None)
            fitted_log_signal = design @ coefficients
            log_residuals = log_warmup - fitted_log_signal
            log_residual_std = max(self._robust_std(log_residuals), 5e-3)
            log_residual_variances.append(log_residual_std * log_residual_std)

        return np.diag(log_residual_variances)

    def _warn_if_warmup_may_take_too_long(self) -> None:
        if (
            config.getint("growth_rate_calculating.config", "samples_for_od_statistics", fallback=35)
            / config.getfloat("od_reading.config", "samples_per_second", fallback=0.2)
        ) >= 600:
            self.logger.warning(
                "Due to the low `samples_per_second`, and high `samples_for_od_statistics` needed to establish a baseline, initial growth rate and nOD may take over 10 minutes to show up."
            )

    def _compute_od_statistics_from_warmup_events(
        self, warmup_events: list[structs.ODReadings]
    ) -> tuple[dict[pt.PdChannel, float], dict[pt.PdChannel, float]]:
        import numpy as np

        observations_by_channel: dict[pt.PdChannel, list[float]] = defaultdict(list)
        for event in warmup_events:
            for channel, reading in event.ods.items():
                observations_by_channel[channel].append(float(reading.od))

        means = {
            channel: float(np.median(np.asarray(observations, dtype=float)))
            for channel, observations in observations_by_channel.items()
        }
        variances = {
            channel: float(max(self._robust_std(np.asarray(observations, dtype=float)) ** 2, 1e-12))
            for channel, observations in observations_by_channel.items()
        }
        self.logger.debug(f"measured mean: {means}")
        self.logger.debug(f"measured variances: {variances}")
        self.logger.info("Completed OD normalization metrics.")
        return means, variances

    def _get_initial_values_from_warmup_observations(
        self, warmup_observations: list[dict[pt.PdChannel, float]]
    ) -> tuple[float, float]:
        fused_observations = self._fuse_warmup_observations(warmup_observations)
        initial_nod = median(fused_observations[-5:])
        initial_growth_rate = 0.0
        return initial_nod, initial_growth_rate

    @staticmethod
    def _robust_std(values: Any) -> float:
        import numpy as np

        array = np.asarray(values, dtype=float)
        if array.size == 0:
            return 0.0
        median_ = float(np.median(array))
        mad = float(np.median(np.abs(array - median_)))
        return 1.4826 * mad

    @staticmethod
    def _fuse_warmup_observations(warmup_observations: list[dict[pt.PdChannel, float]]) -> list[float]:
        return [mean(warmup_observation.values()) for warmup_observation in warmup_observations]

    def _get_precomputed_normalization_factors(
        self, warmup_events: list[structs.ODReadings]
    ) -> dict[pt.PdChannel, float]:
        try:
            od_normalization_factors = self._get_od_normalization_from_cache()
            if not od_normalization_factors:
                raise KeyError("Empty cached normalization statistics.")
            self.logger.debug("Loaded OD normalization factors from cache.")
        except KeyError:
            self.logger.info("OD normalization factors not found in cache. Computing them now.")
            od_normalization_factors, od_variances = self._compute_od_statistics_from_warmup_events(
                warmup_events
            )
            with local_persistent_storage("od_normalization_mean") as cache:
                cache[self.experiment] = dumps(od_normalization_factors)
            self.logger.debug("Cached OD normalization factors computed from warmup observations.")
            if any(v == 0.0 for v in od_variances.values()):
                self.logger.error(
                    "OD variance is zero - this suggests that the OD sensor is not working properly, or a calibration is wrong."
                )

        return od_normalization_factors

    def _get_od_normalization_from_cache(self) -> dict[pt.PdChannel, float]:
        with local_persistent_storage("od_normalization_mean") as cache:
            return cast(dict[pt.PdChannel, float], cache.getjson(self.experiment))

    def scale_raw_observations(self, od_readings: structs.ODReadings) -> dict[pt.PdChannel, float]:
        scaled_signals = {
            channel: od_readings.ods[channel].od / self.od_normalization_factors[channel]
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
                dt = self.expected_dt

            self.time_of_previous_observation = timestamp

        updated_state_, covariance_ = self.ekf.update(
            list(scaled_observations.values()), dt, self._recent_dilution
        )
        updated_state = cast(Any, updated_state_)
        covariance = cast(Any, covariance_)
        latest_od_filtered = exp(float(updated_state[0]))
        latest_growth_rate = float(updated_state[1])

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
            state=cast(Any, self.ekf.state_).tolist(),
            covariance_matrix=covariance.tolist(),
            timestamp=timestamp,
        )

        return od_readings, (growth_rate, od_filtered, kf_outputs)

    def _respond_to_dosing_event(self, dosing_event: structs.DosingEvent) -> None:
        self._obs_since_last_dose = 0
        self._obs_required_to_reset = 2
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
        assert od_stream.is_live and dosing_stream.is_live
        od_events_iter = self._initialize_state_and_get_od_iterator(od_stream, dosing_stream)

        merged_streams = merge_live_streams(od_events_iter, dosing_stream, stop_event=self._blocking_event)

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

        self._warn_if_warmup_may_take_too_long()
        od_events_iter = iter(od_stream)
        self.logger.info("Collecting warmup OD observations for growth-rate initialization.")
        warmup_events, od_events_iter = self.collect_warmup_events(
            od_events_iter,
            config.getint("growth_rate_calculating.config", "samples_for_od_statistics", fallback=35),
        )
        self.logger.debug(f"Collected {len(warmup_events)} warmup OD observations.")
        self.od_normalization_factors = self._get_precomputed_normalization_factors(warmup_events)

        self.logger.debug(f"od_normalization_mean={self.od_normalization_factors}")

        warmup_observations = self.scale_warmup_events(warmup_events)
        self.ekf = self._initialize_extended_kalman_filter(warmup_observations)
        self._initialization_complete.set()
        return od_events_iter

    def collect_warmup_events(
        self,
        od_iter: Iterator[structs.ODReadings],
        n_warmup_observations: int,
    ) -> tuple[list[structs.ODReadings], Iterator[structs.ODReadings]]:
        warmup_events: list[structs.ODReadings] = []

        for _ in range(max(n_warmup_observations, 1)):
            try:
                warmup_events.append(next(od_iter))
            except StopIteration:
                break

        if not warmup_events:
            raise IndexError("Expected at least one OD observation to initialize growth-rate filter.")

        return warmup_events, od_iter

    def scale_warmup_events(
        self,
        warmup_events: list[structs.ODReadings],
    ) -> list[dict[pt.PdChannel, float]]:
        self.logger.debug("Replaying warmup OD observations into the live stream.")
        warmup_observations = [self.scale_raw_observations(event) for event in warmup_events]
        self.logger.debug(f"Warmup OD observations: {warmup_observations}")
        return warmup_observations


@click.group(invoke_without_command=True, name="growth_rate_calculating")
@click.pass_context
def click_growth_rate_calculating(ctx: click.Context) -> None:
    """
    Start calculating growth rate
    """
    if ctx.invoked_subcommand is None:
        unit = whoami.get_unit_name()
        experiment = whoami.get_assigned_experiment_name(unit)

        use_fused_od = _should_use_fused_od(unit)
        od_stream: MqttODSource | MqttODFusedSource
        if use_fused_od:
            od_stream = MqttODFusedSource(unit=unit, experiment=experiment, skip_first=5)
        else:
            od_stream = MqttODSource(unit=unit, experiment=experiment, skip_first=5)
        dosing_stream = MqttDosingSource(unit=unit, experiment=experiment)

        with GrowthRateCalculator(
            unit=unit,
            experiment=experiment,
        ) as job:
            for _ in job.process_until_disconnected_or_exhausted(
                od_stream=od_stream, dosing_stream=dosing_stream
            ):
                continue


@click_growth_rate_calculating.command(name="clear_cache")
def click_clear_cache() -> None:
    unit = whoami.get_unit_name()
    experiment = whoami.get_assigned_experiment_name(unit)

    with local_persistent_storage("od_normalization_mean") as cache:
        cache.pop(experiment)
