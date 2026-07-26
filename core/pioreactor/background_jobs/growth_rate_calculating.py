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
from collections.abc import Iterator
from datetime import datetime
from math import exp
from math import log
from queue import Empty
from queue import Queue
from statistics import mean
from statistics import median
from typing import Any
from typing import cast
from typing import TYPE_CHECKING

import click
from msgspec import DecodeError
from msgspec.json import decode
from msgspec.json import encode as dumps
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.config import config
from pioreactor.utils import local_persistent_storage

if TYPE_CHECKING:
    from grpredict import CultureGrowthEKF

FUSED_PD_CHANNEL: pt.PdChannel = "1"
FUSED_PD_ANGLE: pt.PdAngle = "90"
INITIAL_OD_OBSERVATIONS_TO_SKIP = 5
POST_DOSE_OBSERVATIONS = 2


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
    }

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
    ):
        samples_per_second = config.getfloat("od_reading.config", "samples_per_second")
        if samples_per_second <= 0:
            raise ValueError(
                f"Invalid [od_reading.config] samples_per_second={samples_per_second}. Expected a value > 0."
            )

        samples_for_od_statistics = config.getint(
            "growth_rate_calculating.config",
            "samples_for_od_statistics",
        )
        if samples_for_od_statistics < 1:
            raise ValueError(
                "Invalid [growth_rate_calculating.config] "
                f"samples_for_od_statistics={samples_for_od_statistics}. Expected a value >= 1."
            )

        ekf_outlier_std_threshold = config.getfloat(
            "growth_rate_calculating.config",
            "ekf_outlier_std_threshold",
        )
        if ekf_outlier_std_threshold <= 2.0:
            raise ValueError(
                "Invalid [growth_rate_calculating.config] "
                f"ekf_outlier_std_threshold={ekf_outlier_std_threshold}. Expected a value > 2."
            )

        super().__init__(unit=unit, experiment=experiment)

        self.time_of_previous_observation: datetime | None = None
        self.expected_dt = 1 / (60 * 60 * samples_per_second)  # in hours
        self.samples_for_od_statistics = samples_for_od_statistics
        self.ekf_outlier_std_threshold = ekf_outlier_std_threshold
        self._post_dose_observations_remaining = 0

        # runtime state initialized during processing
        self.ekf: CultureGrowthEKF | None = None
        self.od_normalization_factors: dict[pt.PdChannel, float] = {}
        self.growth_rate: structs.GrowthRate | None = None
        self.od_filtered: structs.ODFiltered | None = None

        self._use_fused_od = _should_use_fused_od(unit)
        self._od_topic = (
            f"pioreactor/{unit}/{experiment}/od_reading/od_fused"
            if self._use_fused_od
            else f"pioreactor/{unit}/{experiment}/od_reading/ods"
        )
        self._dosing_topic = f"pioreactor/{unit}/{experiment}/dosing_events"
        self._growth_rate_event_messages: Queue[pt.MQTTMessage] = Queue()

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(
            self._growth_rate_event_messages.put,
            [self._od_topic, self._dosing_topic],
            allow_retained=False,
        )

    def stream_mqtt_growth_rate_events(self) -> Iterator[structs.ODReadings | structs.DosingEvent]:
        od_message_count = 0

        while not self._blocking_event.is_set():
            try:
                message = self._growth_rate_event_messages.get(timeout=0.1)
            except Empty:
                continue

            try:
                if message.topic == self._dosing_topic:
                    yield decode(message.payload, type=structs.DosingEvent)
                    continue

                if message.topic != self._od_topic:
                    raise ValueError(f"Unexpected MQTT topic: {message.topic}")

                od_message_count += 1
                if od_message_count <= INITIAL_OD_OBSERVATIONS_TO_SKIP:
                    continue

                if self._use_fused_od:
                    fused = decode(message.payload, type=structs.ODFused)
                    yield structs.ODReadings(
                        timestamp=fused.timestamp,
                        ods={
                            FUSED_PD_CHANNEL: structs.RawODReading(
                                timestamp=fused.timestamp,
                                angle=FUSED_PD_ANGLE,
                                od=fused.od_fused,
                                channel=FUSED_PD_CHANNEL,
                                ir_led_intensity=0.0,
                            )
                        },
                    )
                else:
                    yield decode(message.payload, type=structs.ODReadings)
            except DecodeError as error:
                self.logger.warning(f"Failed to decode message: {error}")
                continue

    def _initialize_extended_kalman_filter(
        self, warmup_observations: list[dict[pt.PdChannel, float]]
    ) -> CultureGrowthEKF:
        from grpredict import CultureGrowthEKF
        import numpy as np

        self.logger.info("Initializing growth-rate filter from warmup observations.")
        observation_noise_covariance = self._create_obs_noise_covariance_from_warmup_observations(
            warmup_observations
        )
        self.logger.debug(f"Observation noise covariance matrix:\n{repr(observation_noise_covariance)}")
        self.logger.debug(f"{self.ekf_outlier_std_threshold=}")

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
            self.ekf_outlier_std_threshold,
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
                [warmup_observation[channel] for channel in self._ordered_pd_channels()]
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

    def _ordered_pd_channels(self) -> tuple[pt.PdChannel, ...]:
        return tuple(sorted(self.od_normalization_factors, reverse=True))

    def scale_raw_observations(self, od_readings: structs.ODReadings) -> dict[pt.PdChannel, float]:
        zero_reference_channels = [
            channel
            for channel in self._ordered_pd_channels()
            if self.od_normalization_factors[channel] <= 0.0
        ]
        if zero_reference_channels:
            raise ValueError(
                f"Non-positive OD normalization factor(s) for channel(s) {zero_reference_channels}: {self.od_normalization_factors}"
            )

        scaled_signals = {
            channel: od_readings.ods[channel].od / self.od_normalization_factors[channel]
            for channel in self._ordered_pd_channels()
        }

        if any(v <= 0.0 for v in scaled_signals.values()):
            raise ValueError(
                f"Non-positive normalized value(s) observed: {scaled_signals}. Likely optical signal received is less than the blank signal or OD reading is 0."
            )

        return scaled_signals

    def compute_dt_hours(self, timestamp: datetime) -> float:
        if whoami.is_testing_env():
            # when running a mock script, we run at an accelerated rate, but want to mimic
            # production.
            return self.expected_dt

        if self.time_of_previous_observation is None:
            self.time_of_previous_observation = timestamp
            return self.expected_dt

        dt = (timestamp - self.time_of_previous_observation).total_seconds() / 60 / 60
        if dt < 0:
            self.logger.debug(f"Late arriving data: {timestamp=}, {self.time_of_previous_observation=}")
            raise ValueError(f"Late arriving data: {timestamp=}, {self.time_of_previous_observation=}")

        self.time_of_previous_observation = timestamp
        return dt

    def _update_state_from_observation(
        self, od_readings: structs.ODReadings
    ) -> tuple[structs.GrowthRate, structs.ODFiltered]:
        timestamp = od_readings.timestamp
        scaled_observations = self.scale_raw_observations(od_readings)
        dt = self.compute_dt_hours(timestamp)
        is_recent_dilution = self._post_dose_observations_remaining > 0

        assert self.ekf is not None
        updated_state_, _ = self.ekf.update(
            list(scaled_observations.values()),
            dt,
            is_recent_dilution,
        )
        updated_state = cast(Any, updated_state_)
        if is_recent_dilution:
            self._post_dose_observations_remaining -= 1

        return (
            structs.GrowthRate(
                growth_rate=float(updated_state[1]),
                timestamp=timestamp,
            ),
            structs.ODFiltered(
                od_filtered=exp(float(updated_state[0])),
                timestamp=timestamp,
            ),
        )

    def block_until_disconnected(self) -> None:
        events = self.stream_mqtt_growth_rate_events()

        if self.samples_for_od_statistics * self.expected_dt * 60 * 60 >= 600:
            self.logger.warning(
                "Due to the low `samples_per_second`, and high `samples_for_od_statistics` needed to establish a baseline, initial growth rate and nOD may take over 10 minutes to show up."
            )

        self.logger.info("Collecting warmup OD observations for growth-rate initialization.")
        warmup_events = self.collect_warmup_events(events)
        if self._blocking_event.is_set():
            return

        self.logger.debug(f"Collected {len(warmup_events)} warmup OD observations.")
        self.od_normalization_factors = self._get_precomputed_normalization_factors(warmup_events)
        self.logger.debug(f"od_normalization_mean={self.od_normalization_factors}")

        try:
            self.logger.debug("Replaying warmup OD observations into the live stream.")
            warmup_observations = [self.scale_raw_observations(event) for event in warmup_events]
            self.logger.debug(f"Warmup OD observations: {warmup_observations}")
        except ValueError as error:
            self.logger.error(f"Error processing warmup OD readings: {error}", exc_info=True)
            raise
        self.ekf = self._initialize_extended_kalman_filter(warmup_observations)

        for event in events:
            if isinstance(event, structs.DosingEvent):
                self._post_dose_observations_remaining = POST_DOSE_OBSERVATIONS
                continue

            try:
                self.growth_rate, self.od_filtered = self._update_state_from_observation(event)
            except ValueError as error:
                self.logger.error(f"Error processing OD readings: {error}", exc_info=True)

        if not self._blocking_event.is_set():
            raise RuntimeError("Growth-rate event stream stopped before job shutdown.")

    def collect_warmup_events(
        self,
        events_iter: Iterator[structs.ODReadings | structs.DosingEvent],
    ) -> list[structs.ODReadings]:
        warmup_events: list[structs.ODReadings] = []

        while len(warmup_events) < self.samples_for_od_statistics:
            try:
                event = next(events_iter)
            except StopIteration:
                if self._blocking_event.is_set():
                    return warmup_events
                raise RuntimeError("Growth-rate event stream stopped before job shutdown.")

            if isinstance(event, structs.DosingEvent):
                self.logger.info("Dosing event observed during warmup. Restarting OD observation collection.")
                warmup_events.clear()
            else:
                warmup_events.append(event)

        return warmup_events


@click.group(invoke_without_command=True, name="growth_rate_calculating")
@click.pass_context
def click_growth_rate_calculating(ctx: click.Context) -> None:
    """
    Start calculating growth rate
    """
    if ctx.invoked_subcommand is None:
        unit = whoami.get_unit_name()
        experiment = whoami.get_assigned_experiment_name(unit)

        with GrowthRateCalculator(
            unit=unit,
            experiment=experiment,
        ) as job:
            job.block_until_disconnected()


@click_growth_rate_calculating.command(name="clear_cache")
def click_clear_cache() -> None:
    unit = whoami.get_unit_name()
    experiment = whoami.get_assigned_experiment_name(unit)

    with local_persistent_storage("od_normalization_mean") as cache:
        cache.pop(experiment)
