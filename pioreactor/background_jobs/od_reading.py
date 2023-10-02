# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a turbidity reading, which is a proxy for OD).
Topics published to

    pioreactor/<unit>/<experiment>/od_reading/od/<channel>

Ex:

    pioreactor/pioreactor1/trial15/od_reading/od/1

a json blob like:

    {
        "voltage": 0.10030799136835057,
        "timestamp": "2021-06-06T15:08:12.080594",
        "angle": "90,135"
    }


All signals published together to

    pioreactor/<unit>/<experiment>/od_reading/ods

a serialized json blob like:

    {
      "ods": {
        "2": {
          "od": 0.1008556663221068,
          "angle": "135,45"
        },
        "1": {
          "od": 0.10030799136835057,
          "angle": "90,135"
        }
      },
      "timestamp": "2021-06-06T15:08:12.081153"
    }


Internally, the ODReader runs a function every `interval` seconds. The function
 1. turns off all non-IR LEDs
 2. turns on the IR LED
 3. calls ADCReader to read channels from the ADC.
 4. Performs any transformations (see below)
 5. Switches back LEDs to previous state from step 1.
 6. Publishes data to MQTT

Dataflow of raw signal to final output:

┌──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ODReader                                                                                                                  │
│                                                                                                                          │
│                                                                                                                          │
│   ┌──────────────────────────────────────────────────────────┐  ┌────────────────────────┐  ┌────────────────────────┐   │
│   │ADCReader                                                 │  │IrLedReferenceTracker   │  │CalibrationTransformer  │   │
│   │                                                          │  │                        │  │                        │   │
│   │                                                          │  │                        │  │                        │   │
│   │ ┌──────────────┐   ┌──────────────┐    ┌───────────────┐ │  │  ┌─────────────────┐   │  │  ┌─────────────────┐   │   │
│   │ │              ├───►              ├────►               │ │  │  │                 │   │  │  │                 │   │   │
│   │ │              │   │              │    │               │ │  │  │                 │   │  │  │                 │   │   │
│   │ │ samples from ├───►   ADC offset ├────►      sin      ├─┼──┼──►  IR output      ├───┼──┼──►  Transform via  ├───┼───┼───►
│   │ │     ADC      │   │    removed   │    │   regression  │ │  │  │  compensation   │   │  │  │  calibration    │   │   │
│   │ │              ├───►              ├────►               │ │  │  │                 │   │  │  │  curve          │   │   │
│   │ └──────────────┘   └──────────────┘    └───────────────┘ │  │  └─────────────────┘   │  │  │  (or no-op)     │   │   │
│   │                                                          │  │                        │  │  └─────────────────┘   │   │
│   │                                                          │  │                        │  │                        │   │
│   └──────────────────────────────────────────────────────────┘  └────────────────────────┘  └────────────────────────┘   │
│                                                                                                                          │
│                                                                                                                          │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

In the ODReader class, we publish the `first_od_obs_time` to MQTT so other jobs can read it and
make decisions. For example, if a bubbler/visible light LED is active, it should time itself
s.t. it is _not_ running when an turbidity measurement is about to occur. See BackgroundJobWithDodging class.

"""
from __future__ import annotations

import math
import os
import threading
import types
from time import sleep
from time import time
from typing import Callable
from typing import cast
from typing import Optional

import click
from msgspec.json import decode
from msgspec.json import encode

import pioreactor.actions.led_intensity as led_utils
from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.base import LoggerMixin
from pioreactor.config import config
from pioreactor.hardware import ADC_CHANNEL_FUNCS
from pioreactor.pubsub import publish
from pioreactor.pubsub import QOS
from pioreactor.utils import argextrema
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import local_persistant_storage
from pioreactor.utils import timing
from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.utils.streaming_calculations import ExponentialMovingStd
from pioreactor.utils.timing import catchtime

ALL_PD_CHANNELS: list[pt.PdChannel] = ["1", "2"]
VALID_PD_ANGLES: list[pt.PdAngle] = ["45", "90", "135", "180"]
PdChannelToVoltage = dict[pt.PdChannel, pt.Voltage]

REF_keyword = "REF"
IR_keyword = "IR"


def average_over_pd_channel_to_voltages(*pd_channel_to_voltages: PdChannelToVoltage):
    running_count = 0
    summed_pd_channel_to_voltage: PdChannelToVoltage = {}
    for pd_channel_to_voltage in pd_channel_to_voltages:
        for channel, voltage in pd_channel_to_voltage.items():
            summed_pd_channel_to_voltage[channel] = (
                summed_pd_channel_to_voltage.get(channel, 0) + voltage
            )
        running_count += 1

    return {
        channel: voltage / running_count
        for channel, voltage in summed_pd_channel_to_voltage.items()
    }


class ADCReader(LoggerMixin):
    _logger_name = "adc_reader"
    _setup_complete = False

    def __init__(
        self,
        channels: list[pt.PdChannel],
        fake_data: bool = False,
        interval: Optional[float] = 1.0,
        dynamic_gain: bool = True,
        penalizer: float = 700.0,
        oversampling_count: int = 30,
    ) -> None:
        super().__init__()
        self.fake_data = fake_data
        self.dynamic_gain = dynamic_gain
        self.max_signal_moving_average = ExponentialMovingAverage(alpha=0.05)
        self.channels: list[pt.PdChannel] = channels
        self.batched_readings: PdChannelToVoltage = {}
        self.adc_offsets: dict[pt.PdChannel, pt.AnalogValue] = {}
        self.penalizer = penalizer
        self.oversampling_count = oversampling_count

        self.interval = interval
        if "local_ac_hz" in config["od_config"]:
            self.most_appropriate_AC_hz: Optional[float] = config.getfloat(
                "od_config", "local_ac_hz"
            )
        else:
            self.most_appropriate_AC_hz = None

    def setup_adc(self) -> ADCReader:
        """
        This configures the ADC for reading, performs an initial read, and sets variables based on that reading.

        It doesn't occur in the classes __init__ because it often requires an LED to be on (and this class doesn't control LEDs.).
        See ODReader for an example.

        """

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        if self.fake_data:
            from pioreactor.utils.mock import Mock_ADC as ADC
        else:
            from pioreactor.utils.adcs import ADC  # type: ignore

        self.adc = ADC()
        self.logger.debug(f"Using ADC class {self.adc.__class__.__name__}.")

        max_signal = 0.0
        for pd_channel in self.channels:
            adc_channel = ADC_CHANNEL_FUNCS[pd_channel]
            max_signal = max(
                self.adc.from_raw_to_voltage(self.adc.read_from_channel(adc_channel)), max_signal
            )
            self.check_on_max(max_signal)

        # we will instantiate and sweep through to set the gain
        # check if using correct gain
        if self.dynamic_gain:
            self.adc.check_on_gain(max_signal)

        self._setup_complete = True
        self.logger.debug(
            f"ADC ready to read from PD channels {', '.join(map(str, self.channels))}, with gain {self.adc.gain}."
        )
        return self

    def set_offsets(self, batched_readings: PdChannelToVoltage) -> None:
        """
        With the IR LED off, determine the offsets. These offsets are used later to shift the raw signals such that "dark" is 0.
        """
        for channel, blank_reading in batched_readings.items():
            self.adc_offsets[channel] = self.adc.from_voltage_to_raw(blank_reading)

        self.logger.debug(
            f"ADC offsets: {self.adc_offsets}, and in voltage: { {c: self.adc.from_raw_to_voltage(i) for c, i in  self.adc_offsets.items()}}"
        )

    def check_on_max(self, value: pt.Voltage) -> None:
        if value > 3.2:
            self.logger.error(
                f"An ADC channel is recording a very high voltage, {round(value, 2)}V. We are shutting down components and jobs to keep the ADC safe."
            )

            unit, exp = whoami.get_unit_name(), whoami.get_latest_experiment_name()

            with local_intermittent_storage("led_locks") as cache:
                for c in led_utils.ALL_LED_CHANNELS:
                    cache.pop(c)

            # turn off all LEDs that might be causing problems
            # however, ODReader may turn on the IR LED again.
            led_utils.led_intensity(
                {c: 0.0 for c in led_utils.ALL_LED_CHANNELS},
                source_of_event="ADCReader",
                unit=unit,
                experiment=exp,
                verbose=True,
            )

            publish(
                f"pioreactor/{unit}/{exp}/monitor/flicker_led_with_error_code",
                error_codes.ADC_INPUT_TOO_HIGH,
            )
            # kill ourselves - this will hopefully kill ODReader.
            # we have to send a signal since this is often called in a thread (timing.RepeatedTimer)
            import os
            import signal

            os.kill(os.getpid(), signal.SIGTERM)
            return

        elif value > 3.0:
            self.logger.warning(
                f"An ADC channel is recording a very high voltage, {round(value, 2)}V. It's recommended to keep it less than 3.0V. Suggestion: decrease the IR intensity, or change the PD angle to a lower angle."
            )
            publish(
                f"pioreactor/{whoami.get_unit_name()}/{whoami.get_latest_experiment_name()}/monitor/flicker_led_with_error_code",
                error_codes.ADC_INPUT_TOO_HIGH,
            )
            return

    def _sin_regression_with_known_freq(
        self,
        x: list[float],
        y: list[pt.Voltage],
        freq: float,
        prior_C: Optional[pt.Voltage] = None,
        penalizer_C: Optional[pt.Voltage] = 0,
    ) -> tuple[tuple[pt.Voltage, Optional[float], Optional[float]], float]:
        r"""
        Assumes a known frequency.
        Formula is

        f(t) = C + A*sin(2*pi*freq*t + phi)

        # TODO: is it implemented as C - A*sin(2*pi*freq*t - phi) ??


        However, estimation occurs as:

        \sum_k (f(t_i) - y_i)^2 + penalizer_C * (C - prior_C)^2

        Parameters
        -----------
        x: iterable
        y: iterable
        freq: the frequency
        prior_C: scalar (optional)
            specify value that will be compared against using ridge regression.
        penalizer_C: scalar (optional)
            penalizer values for the ridge regression

        Returns
        ---------
        (C, A, phi):
            tuple of scalars
        AIC: float
            the AIC of the fit, used for model comparison


        Reference
        ------------
        https://scikit-guess.readthedocs.io/en/latest/appendices/references.html#concept


        Notes
        ------
        This clips the max and min values from the input.

        """
        import numpy as np

        assert len(x) == len(y), "shape mismatch"

        # remove the max and min values.
        argmin_y_, argmax_y_ = argextrema(y)

        x = [v for (i, v) in enumerate(x) if (i != argmin_y_) and (i != argmax_y_)]
        y = [v for (i, v) in enumerate(y) if (i != argmin_y_) and (i != argmax_y_)]

        x_ = np.asarray(x)
        y_ = np.asarray(y)
        n = x_.shape[0]

        tau = 2 * np.pi
        sin_x = np.sin(freq * tau * x_)
        cos_x = np.cos(freq * tau * x_)

        sum_sin = sin_x.sum()
        sum_cos = cos_x.sum()
        sum_sin2 = (sin_x**2).sum()
        sum_cos2 = (cos_x**2).sum()
        sum_cossin = (cos_x * sin_x).sum()

        sum_y = y_.sum()
        sum_ysin = (y_ * sin_x).sum()
        sum_ycos = (y_ * cos_x).sum()

        rhs_penalty_term = 0.0
        lhs_penalty_term = 0.0

        if prior_C and penalizer_C:
            rhs_penalty_term = penalizer_C * prior_C
            lhs_penalty_term = penalizer_C

        M = np.array(
            [
                [n + lhs_penalty_term, sum_sin, sum_cos],
                [sum_sin, sum_sin2, sum_cossin],
                [sum_cos, sum_cossin, sum_cos2],
            ]
        )
        Y = np.array([sum_y + rhs_penalty_term, sum_ysin, sum_ycos])

        try:
            C, b, c = np.linalg.solve(M, Y)
        except np.linalg.LinAlgError as e:
            self.logger.error(f"Error in regression. {e}")
            self.logger.debug(f"{x=}")
            self.logger.debug(f"{y=}")
            return (y_.mean(), None, None), 1e10

        y_model = C + b * np.sin(freq * tau * x_) + c * np.cos(freq * tau * x_)
        SSE = np.sum((y_ - y_model) ** 2)

        if SSE > 1e-20:
            AIC = n * np.log(SSE / n) + 2 * 3
        else:
            AIC = math.inf

        if np.sqrt(b**2 + c**2) <= 1e-20:
            A = 0
            phi = 0
        else:
            A = np.sqrt(b**2 + c**2)
            phi = np.arcsin(c / np.sqrt(b**2 + c**2))

        return (float(C), float(A), float(phi)), AIC

    def clear_batched_readings(self) -> None:
        """
        Remove all data from batched_readings. This has the effect of removing hysteresis from the inference.
        """
        self.batched_readings = {}

    @staticmethod
    def _remove_offset_from_signal(
        signals: list[pt.AnalogValue], offset: pt.AnalogValue
    ) -> list[pt.AnalogValue]:
        return [x - offset for x in signals]

    def take_reading(self) -> PdChannelToVoltage:
        """
        Sample from the ADS - likely this has been optimized for use for optical density in the Pioreactor system.


        Returns
        ---------
        readings: dict
            a dict with specified channels and their reading
            Ex: {"1": 0.10240, "2": 0.1023459}


        """
        if not self._setup_complete:
            raise ValueError("Must call setup_adc() first.")

        max_signal = -1.0
        oversampling_count = self.oversampling_count

        # we pre-allocate these arrays to make the for loop faster => more accurate
        aggregated_signals: dict[pt.PdChannel, list[pt.AnalogValue]] = {
            channel: [0.0] * oversampling_count for channel in self.channels
        }
        timestamps: dict[pt.PdChannel, list[float]] = {
            channel: [0.0] * oversampling_count for channel in self.channels
        }

        try:
            with catchtime() as time_since_start:
                for counter in range(oversampling_count):
                    with catchtime() as time_sampling_took_to_run:
                        for pd_channel in self.channels:
                            adc_channel = ADC_CHANNEL_FUNCS[pd_channel]
                            timestamps[pd_channel][counter] = time_since_start()
                            aggregated_signals[pd_channel][counter] = self.adc.read_from_channel(
                                adc_channel
                            )

                    sleep(
                        max(
                            0,
                            -time_sampling_took_to_run()  # the time_sampling_took_to_run() reduces the variance by accounting for the duration of each sampling.
                            + 0.85 / (oversampling_count - 1)
                            + 0.0012
                            * (
                                (counter * 0.618034) % 1
                            ),  # this is to artificially jitter the samples, so that we observe less aliasing. That constant is phi.
                        )
                    )

            batched_estimates_: PdChannelToVoltage = {}

            if self.most_appropriate_AC_hz is None:
                self.most_appropriate_AC_hz = self.determine_most_appropriate_AC_hz(
                    timestamps, aggregated_signals
                )

            if os.environ.get("DEBUG") is not None:
                self.logger.debug(f"{timestamps=}")
                self.logger.debug(f"{aggregated_signals=}")

            for channel in self.channels:
                shifted_signals = self._remove_offset_from_signal(
                    aggregated_signals[channel], self.adc_offsets.get(channel, 0.0)
                )
                (
                    best_estimate_of_signal_,
                    *_other_param_estimates,
                ), _ = self._sin_regression_with_known_freq(
                    timestamps[channel],
                    shifted_signals,
                    self.most_appropriate_AC_hz,
                    prior_C=(self.adc.from_voltage_to_raw(self.batched_readings[channel]))
                    if (channel in self.batched_readings)
                    else None,
                    penalizer_C=(self.penalizer / self.oversampling_count / self.interval)
                    if (self.interval is not None and self.interval > 0)
                    else None
                    # arbitrary, but should scale with number of samples, and duration between samples
                )

                # convert to voltage
                best_estimate_of_signal_v = self.adc.from_raw_to_voltage(best_estimate_of_signal_)

                # force value to be non-negative. Negative values can still occur due to the IR LED reference
                batched_estimates_[channel] = max(best_estimate_of_signal_v, 0)

                # check if more than 3.x V, and shut down to prevent damage to ADC.
                # we use max_signal to modify the PGA, too
                max_signal = max(max_signal, best_estimate_of_signal_v)

            self.check_on_max(max_signal)
            self.batched_readings = batched_estimates_

            # the max signal should determine the ADS1x15's gain
            self.max_signal_moving_average.update(max_signal)

            # check if using correct gain
            # this may need to be adjusted for higher rates of data collection
            if self.dynamic_gain:
                m = self.max_signal_moving_average.get_latest()
                assert m is not None
                self.adc.check_on_gain(m)

            return batched_estimates_
        except OSError as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(
                "Detected i2c error - is everything well connected? Check Heating PCB connection & HAT connection."
            )
            raise e
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)
            raise e

    def determine_most_appropriate_AC_hz(
        self,
        timestamps: dict[pt.PdChannel, list[float]],
        aggregated_signals: dict[pt.PdChannel, list[pt.AnalogValue]],
    ) -> float:
        def _compute_best_freq(timestamps, aggregated_signals):
            FREQS_TO_TRY = [60.0, 50.0]
            argmin_freq = FREQS_TO_TRY[0]
            min_AIC = float("inf")

            for freq in FREQS_TO_TRY:
                _, AIC = self._sin_regression_with_known_freq(
                    timestamps, aggregated_signals, freq=freq
                )
                if AIC < min_AIC:
                    min_AIC = AIC
                    argmin_freq = freq

            return argmin_freq

        channel = self.channels[0]
        argmin_freq1 = _compute_best_freq(timestamps[channel], aggregated_signals[channel])

        self.logger.debug(f"AC hz estimate: {argmin_freq1}")
        return argmin_freq1


class IrLedReferenceTracker(LoggerMixin):
    _logger_name = "ir_led_ref"
    channel: pt.PdChannel

    def __init__(self) -> None:
        super().__init__()

    def update(self, ir_output_reading: pt.Voltage) -> None:
        pass

    def pop_reference_reading(self, batched_readings: PdChannelToVoltage) -> pt.Voltage:
        return batched_readings.pop(self.channel)

    def __call__(self, batched_readings: PdChannelToVoltage) -> PdChannelToVoltage:
        return batched_readings

    def transform(self, od_reading: pt.Voltage) -> pt.Voltage:
        return od_reading


class PhotodiodeIrLedReferenceTrackerStaticInit(IrLedReferenceTracker):
    """
    This class contains the logic on how we incorporate the
    direct IR LED output into OD readings.

    Tracking and "normalizing" (see below) the OD signals by the IR LED output is important
    because the OD signal is linearly proportional to the LED output.

    The following are causes of LED output changing:
    - change in temperature of LED, caused by change in ambient temperature, or change in intensity of LED
    - LED dimming over time
    - drop in 3.3V rail -> changes the reference voltage for LED driver -> changes the output

    Unlike other models (see git history), instead of recording the _initial_ led value, we hardcode it to something. Why?
    In PhotodiodeIrLedReferenceTracker (see git history), the transform OD reading is proportional to the initial LED value:

    OD = RAW / (EMA(REF) / initial)
       = initial * ( RAW / EMA(REF) )

    This has problems because as the LED ages, the INITIAL will decrease, and then any calibrations will be start to be off.

    Note: The reason we have INITIAL is so that our transformed OD reading is not some uninterpretable large number (as RAW / REF would be).

    OD = RAW / (EMA(REF) / INITIAL)
       = INITIAL * ( RAW / EMA(REF) )

    Note: INITIAL is just a scale value that makes the data / charts easier to work with. It doesn't (shouldn't) effect anything
    downstream. Note too that as we are normalizing OD readings, the output has arbitrary units.
    """

    INITIAL = 1.0  # TODO: is this the same for version 1.0 HATs and version 1.0+ HATs???

    def __init__(self, channel: pt.PdChannel) -> None:
        super().__init__()
        self.led_output_ema = ExponentialMovingAverage(
            config.getfloat("od_config", "pd_reference_ema")
        )
        self.led_output_emstd = ExponentialMovingStd(alpha=0.95, ema_alpha=0.8)
        self.channel = channel
        self.logger.debug(f"Using PD channel {channel} as IR LED reference.")

    def update(self, ir_output_reading: pt.Voltage) -> None:
        # Note, in extreme circumstances, this can be negative, or even blow up to some large number.
        self.led_output_ema.update(ir_output_reading / self.INITIAL)

        # check if funky things are happening by std. banding
        self.led_output_emstd.update(ir_output_reading / self.INITIAL)
        latest_std = self.led_output_emstd.get_latest()
        if latest_std is not None and latest_std > 0.01:
            self.logger.warning(
                f"The reference PD is very noisy, std={latest_std:.2g}. Is the PD in channel {self.channel} correctly positioned? Is the IR LED behaving as expected?"
            )
            self.led_output_emstd.clear()  # reset it for i) reduce warnings, ii) if the user purposely changed the IR intensity, this is an approx of that

    def __call__(self, batched_readings: PdChannelToVoltage) -> PdChannelToVoltage:
        return {
            ch: self.transform(od_signal)
            for (ch, od_signal) in batched_readings.items()
            if ch != self.channel
        }

    def transform(self, od_reading: pt.Voltage) -> pt.Voltage:
        led_output = self.led_output_ema.get_latest()
        assert led_output is not None
        if led_output <= 0.0:
            raise ValueError(
                "IR Reference is 0.0. Is it connected correctly? Is the IR LED working?"
            )
        return od_reading / led_output


class NullIrLedReferenceTracker(IrLedReferenceTracker):
    def __init__(self) -> None:
        super().__init__()
        self.logger.debug("Not using any IR LED reference.")

    def pop_reference_reading(self, batched_readings: PdChannelToVoltage) -> pt.Voltage:
        return 1.0


class CalibrationTransformer(LoggerMixin):
    _logger_name = "calibration_transformer"

    def __init__(self) -> None:
        super().__init__()

    def __call__(self, batched_readings: PdChannelToVoltage) -> PdChannelToVoltage:
        return batched_readings


class NullCalibrationTransformer(CalibrationTransformer):
    def __init__(self) -> None:
        super().__init__()
        self.logger.debug("Not using any calibration.")


class CachedCalibrationTransformer(CalibrationTransformer):
    def __init__(self, channel_angle_map: dict[pt.PdChannel, pt.PdAngle]) -> None:
        super().__init__()
        self.has_logged_warning = False
        try:
            self.models = self.get_models_from_disk(channel_angle_map)
        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error("Unable to load calibration models", exc_info=True)
            raise e

    def get_models_from_disk(
        self, channel_angle_map: dict[pt.PdChannel, pt.PdAngle]
    ) -> dict[pt.PdChannel, Callable]:
        models: dict[pt.PdChannel, Callable] = {}

        with local_persistant_storage("current_od_calibration") as c:
            for channel, angle in channel_angle_map.items():
                if angle in c:
                    calibration_data = decode(c[angle], type=structs.AnyODCalibration)  # type: ignore
                    name = calibration_data.name

                    # confirm that current IR intensity is the same as when calibration was performed
                    if calibration_data.ir_led_intensity != config.getfloat(
                        "od_config", "ir_led_intensity"
                    ):
                        msg = f"The calibration `{name}` was calibrated with a different IR LED intensity ({calibration_data.ir_led_intensity} vs current: {config.getfloat('od_config', 'ir_led_intensity')}). Either re-calibrate or change the ir_led_intensity in the config.ini."
                        self.logger.error(msg)
                        raise exc.CalibrationError(msg)
                    # confirm that PD channel is the same as when calibration was performed
                    elif calibration_data.pd_channel != channel:
                        msg = f"The calibration `{name}` was calibrated with a different PD channel ({calibration_data.pd_channel} vs current: {channel})."
                        self.logger.error(msg)
                        raise exc.CalibrationError(msg)
                    else:
                        models[channel] = self._hydrate_model(calibration_data)
                        self.logger.debug(f"Using calibration `{name}` for channel {channel}")

                    # confirm that PD channel is the same as when calibration was performed
                    if calibration_data.pd_channel != channel:
                        msg = f"The calibration `{name}` was calibrated with a different PD channel ({calibration_data.pd_channel} vs current: {channel})."
                        self.logger.error(msg)
                        raise exc.CalibrationError(msg)

                else:
                    self.logger.debug(
                        f"No calibration available for channel {channel}, angle {angle}, skipping."
                    )
        return models

    def _hydrate_model(self, calibration_data: structs.ODCalibration) -> Callable[[float], float]:
        if calibration_data.curve_type == "poly":
            """
            Finds the smallest root in the range [minOD, maxOD] calibrated against.

            Note: if the calibration curve is non-monotonic, ie. has a maximum not on the boundary of the range,
            this procedure effectively ignores it.

            """
            from numpy import roots, zeros_like, real

            def calibration(observed_voltage: pt.Voltage) -> pt.OD:
                poly = calibration_data.curve_data_
                min_OD, max_OD = calibration_data.minimum_od600, calibration_data.maximum_od600
                min_voltage, max_voltage = (
                    calibration_data.minimum_voltage,
                    calibration_data.maximum_voltage,
                )

                coef_shift = zeros_like(poly)
                coef_shift[-1] = observed_voltage
                solve_for_poly = poly - coef_shift
                roots_ = roots(solve_for_poly)
                plausible_roots_ = sorted(
                    [real(r) for r in roots_ if (r.imag == 0) and (min_OD <= real(r) <= max_OD)]
                )

                try:
                    # Q: when do I pick the second root? (for unimodal calibration curves)
                    ideal_root = float(plausible_roots_[0])
                    return ideal_root

                except IndexError:
                    if observed_voltage <= min_voltage:
                        # voltage less than the blank recorded during the calibration and the calibration curve doesn't have solutions (ex even-deg poly)
                        # this isn't great, as there is nil noise in the signal.

                        if not self.has_logged_warning:
                            self.logger.warning(
                                f"Signal below suggested calibration range. Trimming signal. Calibrated for OD=[{min_OD:0.3g}, {max_OD:0.3g}], V=[{min_voltage:0.3g}, {max_voltage:0.3g}]. Observed {observed_voltage:0.3f}V."
                            )
                            self.has_logged_warning = True
                        return min_OD

                    else:
                        if not self.has_logged_warning:
                            self.logger.warning(
                                f"Signal outside suggested calibration range. Trimming signal. Calibrated for OD=[{min_OD:0.3g}, {max_OD:0.3g}], V=[{min_voltage:0.3g}, {max_voltage:0.3g}]. Observed {observed_voltage:0.3f}V."
                            )
                            self.has_logged_warning = True
                        return max_OD

        else:

            def calibration(observed_voltage: pt.Voltage) -> pt.OD:
                return observed_voltage

        return calibration

    def __call__(self, batched_readings: PdChannelToVoltage) -> PdChannelToVoltage:
        return {
            ch: self.models[ch](od) if self.models.get(ch) else od
            for ch, od in batched_readings.items()
        }


class ODReader(BackgroundJob):
    """
    Produce a stream of OD readings from the sensors.

    Parameters
    -----------
    channel_angle_map: dict
        dict of (channel: angle) pairs, ex: {1: "135", 2: "90"}
    interval: float
        seconds between readings. If None or 0, then don't periodically read.
    adc_reader: ADCReader
    ir_led_reference_tracker: IrLedReferenceTracker

    Attributes
    ------------
    adc_reader: ADCReader
    ir_led_reference_tracker: ir_led_reference_tracker
    latest_od_readings:
        represents the most recent readings (post transformations)


    Examples
    ---------

    Initializing this class will start reading in the background, if ``interval`` is not ``None``.

    > od_reader = ODReader({'1': '45'}, 5)
    > # readings will start to be published to MQTT, and the latest reading will be available as od_reader.latest_od_readings

    It can also be iterated over:

    > od_reader = ODReader({'1': '45'}, 5)
    > for od_reading in od_reader:
    >    # do things...

    If ``interval`` is ``None`` or 0, then users need to call ``record_from_adc`` manually.

    >> od_reading = od_reader.record_from_adc()

    """

    job_name = "od_reading"
    published_settings = {
        "first_od_obs_time": {"datatype": "float", "settable": False},
        "ir_led_intensity": {"datatype": "float", "settable": True, "unit": "%"},
        "interval": {"datatype": "float", "settable": False, "unit": "s"},
        "relative_intensity_of_ir_led": {"datatype": "float", "settable": False},
    }
    latest_od_readings: structs.ODReadings

    _pre_read: list[Callable] = []
    _post_read: list[Callable] = []

    def __init__(
        self,
        channel_angle_map: dict[pt.PdChannel, pt.PdAngle],
        interval: Optional[float],
        adc_reader: ADCReader,
        unit: str,
        experiment: str,
        ir_led_reference_tracker: Optional[IrLedReferenceTracker] = None,
        calibration_transformer: Optional[CalibrationTransformer] = None,
    ) -> None:
        super(ODReader, self).__init__(unit=unit, experiment=experiment)

        self.adc_reader = adc_reader
        self.channel_angle_map = channel_angle_map
        self.interval = interval

        if ir_led_reference_tracker is None:
            self.ir_led_reference_tracker = NullIrLedReferenceTracker()
        else:
            self.ir_led_reference_tracker = ir_led_reference_tracker  # type: ignore

        if calibration_transformer is None:
            self.calibration_transformer = NullCalibrationTransformer()
        else:
            self.calibration_transformer = calibration_transformer  # type: ignore

        self.first_od_obs_time: Optional[float] = None
        self._set_for_iterating = threading.Event()

        self.ir_channel: pt.LedChannel = self._get_ir_led_channel_from_configuration()
        self.ir_led_intensity: pt.LedIntensityValue = config.getfloat(
            "od_config", "ir_led_intensity"
        )
        if self.ir_led_intensity > 90:
            self.logger.warning(
                f"The value for the IR LED, {self.ir_led_intensity}%, is very high. We suggest a value 90% or less to avoid damaging the LED."
            )

        self.non_ir_led_channels: list[pt.LedChannel] = [
            ch for ch in led_utils.ALL_LED_CHANNELS if ch != self.ir_channel
        ]

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.clean_up()
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        self.logger.debug(
            f"Starting od_reading with PD channels {channel_angle_map}, with IR LED intensity {self.ir_led_intensity}% from channel {self.ir_channel}."
        )

        self.pre_read_callbacks: list[Callable] = self._prepare_pre_callbacks()
        self.post_read_callbacks: list[Callable] = self._prepare_post_callbacks()

        # setup the ADC by turning off all LEDs.
        with led_utils.change_leds_intensities_temporarily(
            {ch: 0.0 for ch in led_utils.ALL_LED_CHANNELS},
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            pubsub_client=self.pub_client,
            verbose=False,
        ):
            with led_utils.lock_leds_temporarily(self.non_ir_led_channels):
                # IR led is on
                self.start_ir_led()
                sleep(0.10)
                self.adc_reader.setup_adc()  # determine best gain, max-signal, etc.

                # IR led is off so we can set blanks
                self.stop_ir_led()
                sleep(0.10)

                avg_blank_reading = average_over_pd_channel_to_voltages(
                    self.adc_reader.take_reading(),
                    self.adc_reader.take_reading(),
                )
                self.adc_reader.set_offsets(avg_blank_reading)  # set dark offset

                # clear the history in adc_reader, so that we don't blank readings in later inference.
                self.adc_reader.clear_batched_readings()

        if (self.interval is not None) and self.interval > 0:
            if self.interval <= 1.0:
                self.logger.warning(
                    f"Recommended to have the interval between readings be larger than 1.0 second. Currently {self.interval} s."
                )

            self.record_from_adc_timer = timing.RepeatedTimer(
                self.interval,
                self.record_from_adc,
                job_name=self.job_name,
                run_immediately=True,
            ).start()

    def _prepare_post_callbacks(self) -> list[Callable]:
        callbacks: list[Callable] = []

        # user created callbacks, this binds the callback to the instance so def cb(self, ... ) makes sense.
        for func in self._post_read:
            setattr(self, func.__name__, types.MethodType(func, self))
            callbacks.append(getattr(self, func.__name__))
        return callbacks

    def _prepare_pre_callbacks(self) -> list[Callable]:
        callbacks: list[Callable] = []

        # user created callbacks, this binds the callback to the instance so def cb(self, ... ) makes sense.
        for func in self._pre_read:
            setattr(self, func.__name__, types.MethodType(func, self))
            callbacks.append(getattr(self, func.__name__))
        return callbacks

    @classmethod
    def add_pre_read_callback(cls, function: Callable):
        cls._pre_read.append(function)

    @classmethod
    def add_post_read_callback(cls, function: Callable):
        cls._post_read.append(function)

    @property
    def ir_led_on_and_rest_off_state(self) -> dict[pt.LedChannel, pt.LedIntensityValue]:
        return {
            channel: (self.ir_led_intensity if channel == self.ir_channel else 0.0)
            for channel in led_utils.ALL_LED_CHANNELS
        }

    def record_from_adc(self) -> structs.ODReadings:
        """
        Take a recording of the current OD of the culture.

        """
        if self.first_od_obs_time is None:
            self.first_od_obs_time = time()

        for pre_function in self.pre_read_callbacks:
            try:
                pre_function()
            except Exception:
                self.logger.debug(f"Error in pre_function={pre_function.__name__}.", exc_info=True)

        # we put a soft lock on the LED channels - it's up to the
        # other jobs to make sure they check the locks.
        with led_utils.change_leds_intensities_temporarily(
            desired_state=self.ir_led_on_and_rest_off_state,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            pubsub_client=self.pub_client,
            verbose=False,
        ):
            with led_utils.lock_leds_temporarily(self.non_ir_led_channels):
                sleep(0.1)
                timestamp_of_readings = timing.current_utc_datetime()
                od_reading_by_channel = self._read_from_adc_and_transform()
                od_readings = structs.ODReadings(
                    timestamp=timestamp_of_readings,
                    ods={
                        channel: structs.ODReading(
                            od=od_reading_by_channel[channel],
                            angle=angle,
                            timestamp=timestamp_of_readings,
                            channel=channel,
                        )
                        for channel, angle in self.channel_angle_map.items()
                    },
                )

        self.latest_od_readings = od_readings

        self._publish_single(self.latest_od_readings)
        self._publish_batch(self.latest_od_readings)
        self._log_relative_intensity_of_ir_led(self.latest_od_readings)
        self._unblock_internal_event()

        for post_function in self.post_read_callbacks:
            try:
                post_function(od_readings)
            except Exception:
                self.logger.debug(
                    f"Error in post_function={post_function.__name__}.", exc_info=True
                )

        return od_readings

    def start_ir_led(self) -> None:
        r = led_utils.led_intensity(
            {self.ir_channel: self.ir_led_intensity},
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            pubsub_client=self.pub_client,
            verbose=False,
        )
        if not r:
            raise OSError("IR LED could not be started. Stopping OD reading.")

        return

    def stop_ir_led(self) -> None:
        led_utils.led_intensity(
            {self.ir_channel: 0.0},
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            pubsub_client=self.pub_client,
            verbose=False,
        )

    ###########
    # Private
    ############

    def on_sleeping(self) -> None:
        self.record_from_adc_timer.pause()

    def on_sleeping_to_ready(self) -> None:
        self.record_from_adc_timer.unpause()

    def on_disconnected(self) -> None:
        try:
            self.record_from_adc_timer.cancel()
        except Exception:
            pass

        # turn off the LED after we have take our last ADC reading..
        try:
            self.stop_ir_led()
        except Exception:
            pass

        # tech debt: clear _pre and _post
        self._pre_read.clear()
        self._post_read.clear()

    def _get_ir_led_channel_from_configuration(self) -> pt.LedChannel:
        try:
            return cast(pt.LedChannel, config.get("leds_reverse", IR_keyword))
        except Exception:
            self.logger.error(
                """`leds` section must contain `IR` value. Ex:
        [leds]
        A=IR
            """
            )
            raise KeyError("`IR` value not found in section.")

    def _read_from_adc_and_transform(self) -> PdChannelToVoltage:
        """
        Read from the ADC. This function normalizes by the IR ref.

        Note
        -----
        The IR LED needs to be turned on for this function to report accurate OD signals.
        """
        batched_readings = self.adc_reader.take_reading()
        ir_output_reading = self.ir_led_reference_tracker.pop_reference_reading(batched_readings)
        self.ir_led_reference_tracker.update(ir_output_reading)

        return self.calibration_transformer(self.ir_led_reference_tracker(batched_readings))

    def _publish_batch(self, od_readings: structs.ODReadings) -> None:
        if self.state != self.READY:
            return

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/ods",
            encode(od_readings),
            qos=QOS.EXACTLY_ONCE,
        )

    def _publish_single(self, od_readings: structs.ODReadings) -> None:
        if self.state != self.READY:
            return

        for channel, _ in self.channel_angle_map.items():
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od/{channel}",
                encode(od_readings.ods[channel]),
                qos=QOS.EXACTLY_ONCE,
            )

    def _log_relative_intensity_of_ir_led(self, od_readings) -> None:
        if od_readings.timestamp.microsecond % 8 == 0:  # some pseudo randomness
            self.relative_intensity_of_ir_led = {
                # represents the relative intensity of the LED.
                "relative_intensity_of_ir_led": 1 / self.ir_led_reference_tracker.transform(1.0),
                "timestamp": od_readings.timestamp,
            }

    def _unblock_internal_event(self) -> None:
        if self.state != self.READY:
            return

        self._set_for_iterating.set()

    def __iter__(self):
        return self

    def __next__(self):
        while self._set_for_iterating.wait():
            self._set_for_iterating.clear()
            assert self.latest_od_readings is not None
            return self.latest_od_readings


def find_ir_led_reference(od_angle_channel1, od_angle_channel2) -> Optional[pt.PdChannel]:
    if od_angle_channel1 == REF_keyword:
        return "1"
    elif od_angle_channel2 == REF_keyword:
        return "2"
    else:
        return None


def create_channel_angle_map(
    od_angle_channel1: Optional[pt.PdAngleOrREF], od_angle_channel2: Optional[pt.PdAngleOrREF]
) -> dict[pt.PdChannel, pt.PdAngle]:
    # Inputs are either None, or a string like "135", "90", "REF", ...
    # Example return dict: {"1": "90", "2": "45"}
    channel_angle_map: dict[pt.PdChannel, pt.PdAngle] = {}

    if od_angle_channel1 and od_angle_channel1 != REF_keyword:
        if od_angle_channel1 not in VALID_PD_ANGLES:
            raise ValueError(
                f"{od_angle_channel1=} is not a valid angle. Must be one of {VALID_PD_ANGLES}"
            )
        od_angle_channel1 = cast(pt.PdAngle, od_angle_channel1)
        channel_angle_map["1"] = od_angle_channel1

    if od_angle_channel2 and od_angle_channel2 != REF_keyword:
        if od_angle_channel2 not in VALID_PD_ANGLES:
            raise ValueError(
                f"{od_angle_channel2=} is not a valid angle. Must be one of {VALID_PD_ANGLES}"
            )

        od_angle_channel2 = cast(pt.PdAngle, od_angle_channel2)
        channel_angle_map["2"] = od_angle_channel2

    return channel_angle_map


def start_od_reading(
    od_angle_channel1: Optional[pt.PdAngleOrREF] = None,
    od_angle_channel2: Optional[pt.PdAngleOrREF] = None,
    interval: Optional[float] = 1 / config.getfloat("od_config", "samples_per_second"),
    fake_data: bool = False,
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    use_calibration: bool = config.getboolean("od_config", "use_calibration"),
) -> ODReader:
    """
    This function prepares ODReader and other necessary transformation objects. It's a higher level API than using ODReader.

    Note on od_angle_channels
    --------------------------

    Position is important for these arguments. If your config looks like:

        [od_config.photodiode_channel]
        1=REF
        2=90

    then the correct syntax is `start_od_reading("REF", "90").

    """

    unit = unit or whoami.get_unit_name()
    experiment = experiment or whoami.get_latest_experiment_name()

    ir_led_reference_channel = find_ir_led_reference(od_angle_channel1, od_angle_channel2)
    channel_angle_map = create_channel_angle_map(od_angle_channel1, od_angle_channel2)
    channels = list(channel_angle_map.keys())

    # use IR LED reference to normalize?
    if ir_led_reference_channel is not None:
        ir_led_reference_tracker = PhotodiodeIrLedReferenceTrackerStaticInit(
            ir_led_reference_channel,
        )
        channels.append(ir_led_reference_channel)
    else:
        ir_led_reference_tracker = NullIrLedReferenceTracker()  # type: ignore

    # use an OD calibration?
    if use_calibration:
        calibration_transformer = CachedCalibrationTransformer(channel_angle_map)
    else:
        calibration_transformer = NullCalibrationTransformer()  # type: ignore

    return ODReader(
        channel_angle_map,
        interval=interval,
        unit=unit,
        experiment=experiment,
        adc_reader=ADCReader(
            channels=channels, fake_data=fake_data, interval=interval, dynamic_gain=not fake_data
        ),
        ir_led_reference_tracker=ir_led_reference_tracker,
        calibration_transformer=calibration_transformer,
    )


@click.command(name="od_reading")
@click.option(
    "--od-angle-channel1",
    default=config.get("od_config.photodiode_channel", "1", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 1, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel2",
    default=config.get("od_config.photodiode_channel", "2", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 2, separated by commas. Don't specify if channel is empty.",
)
@click.option("--fake-data", is_flag=True, help="produce fake data (for testing)")
def click_od_reading(
    od_angle_channel1: pt.PdAngleOrREF,
    od_angle_channel2: pt.PdAngleOrREF,
    fake_data: bool,
):
    """
    Start the optical density reading job
    """
    od = start_od_reading(
        od_angle_channel1,
        od_angle_channel2,
        fake_data=fake_data or whoami.is_testing_env(),
    )
    od.block_until_disconnected()
