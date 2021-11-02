# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a turbidity reading, which is a proxy for OD).
Topics published to

    pioreactor/<unit>/<experiment>/od_reading/od_raw/<channel>

Ex:

    pioreactor/pioreactor1/trial15/od_reading/od_raw/1

a json file like:

    {
        "voltage": 0.10030799136835057,
        "timestamp": "2021-06-06T15:08:12.080594",
        "angle": "90,135"
    }


All signals published together to

    pioreactor/<unit>/<experiment>/od_reading/od_raw_batched

a serialized json like:

    {
      "od_raw": {
        "2": {
          "voltage": 0.1008556663221068,
          "angle": "135,45"
        },
        "1": {
          "voltage": 0.10030799136835057,
          "angle": "90,135"
        }
      },
      "timestamp": "2021-06-06T15:08:12.081153"
      "ir_led_output": 0.01
    }


Internally, the ODReader runs a function every `interval` seconds. The function
 1. turns on the IR LED
 2. calls the subjob ADCReader reads all channels from the ADC.
 3. Turns off LED
 4. Performs any transformations (see below)
 5. Publishes data to MQTT

Transforms are ex: sin regression, and LED output compensation. See diagram below.

Dataflow of raw signal to final output:

┌────────────────────────────────────────────────────────────────────────────────┐
│ODReader                                                                        │
│                                                                                │
│                                                                                │
│   ┌──────────────────────────────────────────┐    ┌────────────────────────┐   │
│   │ADCReader                                 │    │IrLedOutputTracker      │   │
│   │                                          │    │                        │   │
│   │                                          │    │                        │   │
│   │ ┌──────────────┐       ┌───────────────┐ │    │  ┌─────────────────┐   │   │
│   │ │              ├───────►               │ │    │  │                 │   │   │
│   │ │              │       │               │ │    │  │                 │   │   │    MQTT
│   │ │ samples from ├───────►      sin      ├─┼────┼──►  IR output      ├───┼───┼───────►
│   │ │     ADC      │       │   regression  │ │    │  │  compensation   │   │   │
│   │ │              ├───────►               │ │    │  │                 │   │   │
│   │ └──────────────┘       └───────────────┘ │    │  └─────────────────┘   │   │
│   │                                          │    │                        │   │
│   │                                          │    │                        │   │
│   └──────────────────────────────────────────┘    └────────────────────────┘   │
│                                                                                │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘



In the ODReader class, we publish the `first_od_obs_time` to MQTT so other jobs can read it and
make decisions. For example, if a bubbler/visible light LED is active, it should time itself
s.t. it is _not_ running when an turbidity measurement is about to occur.

"""
from __future__ import annotations
from typing import Optional, NewType
from time import time, sleep
import click

from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer, current_utc_time, catchtime
from pioreactor.background_jobs.base import BackgroundJob, LoggerMixin
from pioreactor.actions.led_intensity import (
    led_intensity as change_led_intensity,
    LED_CHANNELS,
    LED_Channel,  # type
    lock_leds_temporarily,
    turn_off_leds_temporarily,
)
from pioreactor.hardware_mappings import SCL, SDA
from pioreactor.pubsub import QOS

PD_Channel = NewType("PD_Channel", int)  # Literal[1,2,3,4]
PD_CHANNELS = [PD_Channel(1), PD_Channel(2), PD_Channel(3), PD_Channel(4)]


class ADCReader(LoggerMixin):
    """


    Notes
    ------
    It's currently highly specific to the ADS1x15 family - a future code
    release may turn ADCReader into an abstract class, and classes like ADS1015Reader
    as subclasses.

    Parameters
    ------------
    channels: list
        a list of channels, a subset of [1, 2, 3, 4]
    fake_data: bool
        generate fake ADC readings internally.
    dynamic_gain: bool
        dynamically change the gain based on the max reading from channels
    initial_gain: number
        set the initial gain - see data sheet for values.

    """

    DATA_RATE: int = 128
    ADS_GAIN_THRESHOLDS = {
        2 / 3: (4.096, 6.144),  # 1 bit = 3mV, for 16bit ADC
        1: (2.048, 4.096),  # 1 bit = 2mV
        2: (1.024, 2.048),  # 1 bit = 1mV
        4: (0.512, 1.024),  # 1 bit = 0.5mV
        8: (0.256, 0.512),  # 1 bit = 0.25mV
        16: (-1, 0.256),  # 1 bit = 0.125mV
    }
    oversampling_count: int = 25
    batched_readings: dict[PD_Channel, float] = {}
    _counter: int = 0

    def __init__(
        self,
        channels: list[PD_Channel],
        fake_data: bool = False,
        dynamic_gain: bool = True,
        initial_gain=1,
    ):
        super().__init__()
        self.fake_data = fake_data
        self.dynamic_gain = dynamic_gain
        self.gain = initial_gain
        self.max_signal_moving_average = ExponentialMovingAverage(alpha=0.05)
        self.channels = channels

        self.logger.debug(
            f"ADC ready to read from PD channels {', '.join(map(str, self.channels))}."
        )

    def setup_adc(self):
        """
        This configures the ADC for reading, performs an initial read, and sets variables based on that reading.

        It doesn't occur in the classes __init__ because it often requires an LED to be on (and this class doesn't control LEDs.).
        See ODReader for an example.
        """

        import adafruit_ads1x15.ads1115 as ADS  # type: ignore

        if self.fake_data:
            from pioreactor.utils.mock import MockAnalogIn as AnalogIn, MockI2C as I2C
        else:
            from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore
            from busio import I2C  # type: ignore

        # we may change the gain dynamically later.
        # TODO: update this to ADS1015 / dynamically choose
        self.ads = ADS.ADS1115(I2C(SCL, SDA), data_rate=self.DATA_RATE)
        self.set_ads_gain(self.gain)

        self.analog_in: dict[PD_Channel, AnalogIn] = {}

        for channel in self.channels:
            self.analog_in[channel] = AnalogIn(
                self.ads, channel - 1
            )  # subtract 1 because we use 1-indexing

        # check if using correct gain
        # this may need to be adjusted for higher rates of data collection
        if self.dynamic_gain:
            max_signal = 0
            # we will instantiate and sweep through to set the gain
            for ai in self.analog_in.values():

                raw_signal_ = ai.voltage
                max_signal = max(raw_signal_, max_signal)

            self.check_on_max(max_signal)
            self.check_on_gain(max_signal)

        self._setup_complete = True
        return self

    def check_on_max(self, value: float) -> None:
        if value > 3.1:
            self.logger.error(
                f"An ADC channel is recording a very high voltage, {round(value, 2)}V. We are shutting down components and jobs to keep the ADC safe."
            )

            # turn off all LEDs that might be causing problems
            # however, ODReader may turn on the IR LED again.
            change_led_intensity(
                channels=LED_CHANNELS,
                intensities=[0] * len(LED_CHANNELS),
                source_of_event="ADCReader",
                verbose=True,
            )

            # kill ourselves - this will hopefully kill ODReader.
            import sys

            sys.exit(1)

    def check_on_gain(self, value: float) -> None:
        for gain, (lb, ub) in self.ADS_GAIN_THRESHOLDS.items():
            if (0.925 * lb <= value < 0.925 * ub) and (self.ads.gain != gain):
                self.gain = gain
                self.set_ads_gain(self.gain)
                self.logger.debug(f"ADC gain updated to {self.gain}.")
                break

    def set_ads_gain(self, gain) -> None:
        self.ads.gain = gain  # this assignment checks to see if the gain is allowed.

    def sin_regression_with_known_freq(self, x, y, freq, prior_C=None, penalizer_C=None):
        r"""
        Assumes a known frequency.
        Formula is

        f(t) = C + A*sin(2*pi*freq*t + phi)

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
        https://scikit-guess.readthedocs.io/en/latest/appendices/reei/translation.html#further-optimizations-based-on-estimates-of-a-and-rho


        """
        import numpy as np

        assert len(x) == len(y), "shape mismatch"
        x = np.asarray(x)
        y = np.asarray(y)
        n = x.shape[0]

        tau = 2 * np.pi
        sin_x = np.sin(freq * tau * x)
        cos_x = np.cos(freq * tau * x)

        sum_sin = sin_x.sum()
        sum_cos = cos_x.sum()
        sum_sin2 = (sin_x ** 2).sum()
        sum_cos2 = (cos_x ** 2).sum()
        sum_cossin = (cos_x * sin_x).sum()

        sum_y = y.sum()
        sum_ysin = (y * sin_x).sum()
        sum_ycos = (y * cos_x).sum()

        rhs_penalty_term = 0
        lhs_penalty_term = 0

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
        except np.linalg.LinAlgError:
            self.logger.error("Error in regression:")
            self.logger.debug(f"x={x}")
            self.logger.debug(f"y={y}")
            return (y.mean(), None, None), 0

        y_model = C + b * np.sin(freq * tau * x) + c * np.cos(freq * tau * x)
        SSE = np.sum((y - y_model) ** 2)

        AIC = (
            n * np.log(SSE / n) + 2 * 3
        )  # TODO: this can raise an error RuntimeWarning: divide by zero encountered in log

        A = np.sqrt(b ** 2 + c ** 2)
        phi = np.arcsin(c / np.sqrt(b ** 2 + c ** 2))

        return (C, A, phi), AIC

    def take_reading(self) -> dict[PD_Channel, float]:
        """
        Sample from the ADS - likely this has been optimized for use for optical density in the Pioreactor system.

        Returns
        ---------
        readings: dict
            a dict with specified channels (as ints) and their reading
            Ex: {1: 0.10240, 2: 0.1023459}


        """
        if not self._setup_complete:
            raise ValueError("Must call setup_adc() first.")

        # in case some other process is also using the ADC chip and changes the gain, we want
        # to always confirm our settings before take a snapshot.
        self.set_ads_gain(self.gain)

        self._counter += 1

        _ADS1X15_PGA_RANGE = {  # TODO: delete when ads1015 is in.
            2 / 3: 6.144,
            1: 4.096,
            2: 2.048,
            4: 1.024,
            8: 0.512,
            16: 0.256,
        }
        max_signal = 0

        aggregated_signals: dict[PD_Channel, list[int]] = {
            channel: [] for channel in self.channels
        }
        timestamps: dict[PD_Channel, list[float]] = {
            channel: [] for channel in self.channels
        }

        try:
            with catchtime() as time_since_start:
                for counter in range(self.oversampling_count):
                    with catchtime() as time_sampling_took_to_run:
                        for channel, ai in self.analog_in.items():
                            timestamps[channel].append(time_since_start())
                            # raw_signal_ = ai.voltage

                            # TODO: delete when ADS1015 is in
                            value1115 = ai.value  # int between 0 and 32767
                            value1015 = (
                                value1115 >> 4
                            ) << 4  # int between 0 and 2047, and then blow it back up to int between 0 and 32767
                            aggregated_signals[channel].append(value1015)

                    sleep(
                        max(
                            0,
                            -time_sampling_took_to_run()  # the time_sampling_took_to_run() reduces the variance by accounting for the duration of each sampling.
                            + 0.80 / (self.oversampling_count - 1)
                            + 0.0025
                            * (
                                (counter * 0.618034) % 1
                            ),  # this is to artificially spread out the samples, so that we observe less aliasing. That constant is phi.
                        )
                    )

            batched_estimates_: dict[PD_Channel, float] = {}
            for channel in self.channels:
                print(list(zip(timestamps[channel], aggregated_signals[channel])))
                (
                    best_estimate_of_signal_,
                    *_other_param_estimates,
                ), _ = self.sin_regression_with_known_freq(
                    timestamps[channel],
                    aggregated_signals[channel],
                    60,  # TODO - this should be empirically determined.
                    prior_C=(
                        self.batched_readings[channel]
                        * 32767
                        / _ADS1X15_PGA_RANGE[self.ads.gain]
                    )
                    if (channel in self.batched_readings)
                    else None,
                    penalizer_C=0.5,  # TODO: this penalizer should scale with absolute value of reading, number of samples, and duration between readings...
                )

                # convert to voltage
                best_estimate_of_signal_ = (
                    best_estimate_of_signal_  # TODO: delete when ADS1015 is in.
                    * _ADS1X15_PGA_RANGE[self.ads.gain]
                    / 32767
                )

                batched_estimates_[channel] = max(best_estimate_of_signal_, 0)

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (
                    (self._counter % 2 == 0)
                    and (best_estimate_of_signal_ >= 2.75)
                    and not self.fake_data
                ):
                    self.logger.warning(
                        f"ADC channel {channel} is recording a very high voltage, {round(best_estimate_of_signal_, 2)}V. It's recommended to keep it less than 3.3V."
                    )

                # check if more than 3V, and shut down to prevent damage to ADC.
                # we use max_signal to modify the PGA, too
                max_signal = max(max_signal, best_estimate_of_signal_)
                self.check_on_max(max_signal)

            self.batched_readings = batched_estimates_

            # the max signal should determine the ADS1x15's gain
            if self.dynamic_gain:
                self.max_signal_moving_average.update(max_signal)

            # check if using correct gain
            # this may need to be adjusted for higher rates of data collection
            if self.dynamic_gain and self._counter % 5 == 1:
                self.check_on_gain(self.max_signal_moving_average())

            return batched_estimates_

        except OSError as e:
            # just skip, not sure why this happens when add_media or remove_waste are called.
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)
            raise e

        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)
            raise e


class IrLedReferenceTracker(LoggerMixin):
    def __init__(self):
        super().__init__()

    def update(self, batched_reading: dict[PD_Channel, float]):
        pass

    def set_blank(self, batched_reading: dict[PD_Channel, float]):
        pass

    def __call__(self, od_signal: float) -> float:
        return od_signal


class PhotodiodeIrLedReferenceTracker(IrLedReferenceTracker):
    """
    This class contains the logic on how we incorporate the
    direct IR LED output into OD readings.

    Tracking and "normalizing" (see below) the OD signals by the IR LED output is important
    because the OD signal is linearly proportional to the LED output.

    The following are causes of LED output changing:
    - change in temperature of LED, caused by change in ambient temperature, or change in intensity of LED
    - LED dimming over time
    - drop in 3.3V rail -> changes the reference voltage for LED driver -> changes the output

    Internally, we track the _initial_ led output signal, and use this as a reference value. For example, let's say
    that the blank led output signal (i.e. led intensity is 0%, but we still detect a small value) is 0.0001,
    and the initial led output is 0.1. The latest IR led output is 0.09 (perhaps the ambient temp increased),
    so then we use the factor: (0.09 - 0.0001) / (0.1 - 0.0001) = 0.8998998999

    This factor is then used to normalize OD readings. Let's say the OD reading is 0.45, so the new value
    is 0.45 / 0.8998998999 = 0.500055617

    Inside, we also use an EMA to smooth the LED output readings, to reduce noise in this signal.

    """

    initial_led_output: Optional[float] = None
    blank_reading: float = 0.0

    def __init__(self, channel: PD_Channel):
        super().__init__()
        self.led_output_ema = ExponentialMovingAverage(0.55)
        self.channel = channel
        self.logger.debug(f"Using PD channel {channel} as IR LED reference.")

    def update(self, batched_reading: dict[PD_Channel, float]):
        ir_output_reading = batched_reading[self.channel]
        if self.initial_led_output is None:
            self.initial_led_output = ir_output_reading

        self.led_output_ema.update(
            (ir_output_reading - self.blank_reading)
            / (self.initial_led_output - self.blank_reading)
        )

    def set_blank(self, batched_reading: dict[PD_Channel, float]):
        self.blank_reading = batched_reading[self.channel]

    def __call__(self, od_signal: float) -> float:
        return od_signal / self.led_output_ema()


class NullIrLedReferenceTracker(IrLedReferenceTracker):
    def __init__(self):
        super().__init__()
        self.logger.debug("Not using any IR LED reference.")


class ODReader(BackgroundJob):
    """
    Produce a stream of OD readings from the sensors.

    Parameters
    -----------

    channel_angle_map: dict
        dict of (channel: angle) pairs, ex: {1: "135", 2: "90"}
    adc_reader: ADCReader
    ir_led_reference_tracker

    Attributes
    ------------

    adc_reader: ADCReader
    latest_reading: dict
        represents the most recent dict from the adc_reader

    """

    published_settings = {
        "first_od_obs_time": {"datatype": "float", "settable": False},
        "led_intensity": {"datatype": "float", "settable": True, "unit": "%"},
        "interval": {"datatype": "float", "settable": False},
    }
    latest_reading: dict[PD_Channel, float]

    def __init__(
        self,
        channel_angle_map: dict[PD_Channel, str],
        interval: float,
        adc_reader: ADCReader,
        ir_led_reference_tracker: IrLedReferenceTracker,
        unit: str = None,
        experiment: str = None,
    ) -> None:
        super(ODReader, self).__init__(
            job_name="od_reading", unit=unit, experiment=experiment
        )

        self.adc_reader = adc_reader

        self.first_od_obs_time: Optional[float] = None

        self.channel_angle_map = channel_angle_map
        self.interval = interval
        self.ir_led_reference_tracker = ir_led_reference_tracker

        # start IR led before ADC starts, as it needs it.
        self.led_intensity = config.getfloat("od_config", "ir_intensity")
        self.ir_channel: LED_Channel = self.get_ir_channel_from_configuration()

        self.logger.debug(
            f"Starting od_reading with PD channels {channel_angle_map}, with IR LED intensity {self.led_intensity}% from channel {self.ir_channel}."
        )

        # setup the ADC by turning off all LEDs that might cause problems.
        with lock_leds_temporarily(LED_CHANNELS):
            with turn_off_leds_temporarily(
                LED_CHANNELS,
                unit=self.unit,
                experiment=self.experiment,
                source_of_event=self.job_name,
                pubsub_client=self.pub_client,
                verbose=False,
            ):

                self.start_ir_led()
                self.adc_reader.setup_adc()
                self.stop_ir_led()

        # get blank values, this slightly improves the accuracy of the IR LED output tracker,
        # see that class's docs.
        self.ir_led_reference_tracker.set_blank(self.adc_reader.take_reading())

        self.record_from_adc_timer = RepeatedTimer(
            self.interval,
            self.record_and_publish_from_adc,
            run_immediately=True,
        ).start()

    def get_ir_channel_from_configuration(self) -> LED_Channel:
        try:
            return LED_Channel(config.get("leds_reverse", "ir"))
        except Exception:
            self.logger.error(
                "`leds` section must contain `ir_led`. Ex: \n\n[leds]\nA=ir"
            )
            raise KeyError()

    def record_and_publish_from_adc(self) -> None:

        if self.first_od_obs_time is None:
            self.first_od_obs_time = time()

        pre_duration = 0.01  # turn on LED prior to taking snapshot and wait

        # we put a soft lock on the LED channels - it's up to the
        # other jobs to make sure they check the locks.
        with lock_leds_temporarily(LED_CHANNELS):
            with turn_off_leds_temporarily(
                LED_CHANNELS,
                unit=self.unit,
                experiment=self.experiment,
                source_of_event=self.job_name,
                pubsub_client=self.pub_client,
                verbose=False,
            ):

                self.start_ir_led()
                sleep(pre_duration)

                timestamp_of_readings = current_utc_time()
                batched_readings = self.adc_reader.take_reading()

        self.latest_reading = batched_readings
        self.ir_led_reference_tracker.update(batched_readings)

        self.publish_single(batched_readings, timestamp_of_readings)
        self.publish_batch(batched_readings, timestamp_of_readings)

    def start_ir_led(self) -> None:
        r = change_led_intensity(
            channels=self.ir_channel,
            intensities=self.led_intensity,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            pubsub_client=self.pub_client,
            verbose=False,
        )
        if not r:
            raise ValueError("IR LED could not be started. Stopping OD reading.")

        return

    def stop_ir_led(self) -> None:
        assert change_led_intensity(
            channels=self.ir_channel,
            intensities=0,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            verbose=False,
            pubsub_client=self.pub_client,
        ), "stop_ir_led failed"

    def on_sleeping(self) -> None:
        self.record_from_adc_timer.pause()
        self.stop_ir_led()

    def on_sleeping_to_ready(self) -> None:
        self.start_ir_led()
        self.record_from_adc_timer.unpause()

    def on_disconnect(self) -> None:

        # turn off the LED after we have take our last ADC reading..
        try:
            self.record_from_adc_timer.cancel()
        except Exception:
            pass
        self.stop_ir_led()
        self.clear_mqtt_cache()

    def publish_batch(
        self, batched_ads_readings: dict[PD_Channel, float], timestamp: str
    ) -> None:
        if self.state != self.READY:
            return

        output = {
            "od_raw": dict(),
            "timestamp": timestamp,
        }

        for channel, angle in self.channel_angle_map.items():
            output["od_raw"][channel] = {
                "voltage": self.normalize_by_led_output(batched_ads_readings[channel]),
                "angle": angle,
            }

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw_batched",
            output,
            qos=QOS.EXACTLY_ONCE,
        )

    def publish_single(
        self, batched_ads_readings: dict[PD_Channel, float], timestamp: str
    ) -> None:
        if self.state != self.READY:
            return

        for channel, angle in self.channel_angle_map.items():

            payload = {
                "voltage": self.normalize_by_led_output(batched_ads_readings[channel]),
                "angle": angle,
                "timestamp": timestamp,
            }

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw/{channel}",
                payload,
                qos=QOS.EXACTLY_ONCE,
            )

    def normalize_by_led_output(self, od_signal: float) -> float:
        return self.ir_led_reference_tracker(od_signal)


REF_keyword = "REF"


def find_ir_led_reference(
    od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4
) -> Optional[PD_Channel]:
    if od_angle_channel1 == REF_keyword:
        return PD_Channel(1)
    elif od_angle_channel2 == REF_keyword:
        return PD_Channel(2)
    elif od_angle_channel3 == REF_keyword:
        return PD_Channel(3)
    elif od_angle_channel4 == REF_keyword:
        return PD_Channel(4)
    else:
        return None


def create_channel_angle_map(
    od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4
) -> dict[PD_Channel, str]:
    # Inputs are either None, or a string like "135", "90,45", "REF", ...
    # Example return dict: {1: "90,135", 2: "45,135", 4:"90"}
    channel_angle_map: dict[PD_Channel, str] = {}

    if od_angle_channel1 and od_angle_channel1 != REF_keyword:
        channel_angle_map[PD_Channel(1)] = od_angle_channel1

    if od_angle_channel2 and od_angle_channel2 != REF_keyword:
        channel_angle_map[PD_Channel(2)] = od_angle_channel2

    if od_angle_channel3 and od_angle_channel3 != REF_keyword:
        channel_angle_map[PD_Channel(3)] = od_angle_channel3

    if od_angle_channel4 and od_angle_channel4 != REF_keyword:
        channel_angle_map[PD_Channel(4)] = od_angle_channel4

    return channel_angle_map


def start_od_reading(
    od_angle_channel1: Optional[str] = None,
    od_angle_channel2: Optional[str] = None,
    od_angle_channel3: Optional[str] = None,
    od_angle_channel4: Optional[str] = None,
    sampling_rate: float = 1 / config.getfloat("od_config", "samples_per_second"),
    fake_data: bool = False,
    unit: str = None,
    experiment: str = None,
) -> ODReader:

    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()

    ir_led_reference_channel = find_ir_led_reference(
        od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4
    )
    channel_angle_map = create_channel_angle_map(
        od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4
    )

    channels = list(channel_angle_map.keys())

    ir_led_reference_tracker: IrLedReferenceTracker
    if ir_led_reference_channel is not None:
        ir_led_reference_tracker = PhotodiodeIrLedReferenceTracker(
            ir_led_reference_channel
        )
        channels.append(ir_led_reference_channel)
    else:
        ir_led_reference_tracker = NullIrLedReferenceTracker()

    return ODReader(
        channel_angle_map,
        interval=sampling_rate,
        unit=unit,
        experiment=experiment,
        adc_reader=ADCReader(
            channels=channels,
            fake_data=fake_data,
        ),
        ir_led_reference_tracker=ir_led_reference_tracker,
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
@click.option(
    "--od-angle-channel3",
    default=config.get("od_config.photodiode_channel", "3", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 3, separated by commas. Don't specify if channel is empty.",
)
@click.option(
    "--od-angle-channel4",
    default=config.get("od_config.photodiode_channel", "4", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 4, separated by commas. Don't specify if channel is empty.",
)
@click.option("--fake-data", is_flag=True, help="produce fake data (for testing)")
def click_od_reading(
    od_angle_channel1, od_angle_channel2, od_angle_channel3, od_angle_channel4, fake_data
):
    """
    Start the optical density reading job
    """
    od = start_od_reading(
        od_angle_channel1,
        od_angle_channel2,
        od_angle_channel3,
        od_angle_channel4,
        fake_data=fake_data or is_testing_env(),
    )
    od.block_until_disconnected()
