# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a turbidity reading, which is a proxy for OD).
Topics published to

    pioreactor/<unit>/<experiment>/od_raw/<channel>

Ex:

    pioreactor/pioreactor1/trial15/od_raw/0

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
        "0": {
          "voltage": 0.1008556663221068,
          "angle": "135,45"
        },
        "1": {
          "voltage": 0.10030799136835057,
          "angle": "90,135"
        }
      },
      "timestamp": "2021-06-06T15:08:12.081153"
    }


Internally, the ODReader runs a function every `interval` seconds. The function
 1. turns on the IR LED
 2. calls the subjob ADCReader reads all channels from the ADC.
 3. Turns off LED
 4. Publishes data to MQTT

Transforms are also inside the above, ex: sin regression, and temperature compensation. See diagram below.

Dataflow of raw signal to final output:

┌────────────────────────────────────────────────────────────────────────────────┐
│ODReader                                                                        │
│                                                                                │
│                                                                                │
│   ┌──────────────────────────────────────────┐    ┌────────────────────────┐   │
│   │ADCReader                                 │    │TemperatureCompensator  │   │
│   │                                          │    │                        │   │
│   │                                          │    │                        │   │
│   │ ┌──────────────┐       ┌───────────────┐ │    │  ┌─────────────────┐   │   │
│   │ │              ├───────►               │ │    │  │                 │   │   │
│   │ │              │       │               │ │    │  │                 │   │   │    MQTT
│   │ │ samples from ├───────►      sin      ├─┼────┼──►  temperature    ├───┼───┼───────►
│   │ │     ADC      │       │   regression  │ │    │  │  compensation   │   │   │
│   │ │              ├───────►               │ │    │  │                 │   │   │
│   │ └──────────────┘       └───────────────┘ │    │  └─────────────────┘   │   │
│   │                                          │    │                        │   │
│   │                                          │    │                        │   │
│   └──────────────────────────────────────────┘    └────────────────────────┘   │
│                                                                                │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘



In the ADCReader class, we publish the `first_ads_obs_time` to MQTT so other jobs can read it and
make decisions. For example, if a bubbler/visible light LED is active, it should time itself
s.t. it is _not_ running when an turbidity measurement is about to occur.
"""
import time
import json
import signal

import click

from pioreactor.utils.streaming_calculations import ExponentialMovingAverage
from pioreactor.whoami import get_unit_name, get_latest_experiment_name, is_testing_env
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer, current_utc_time, catchtime
from pioreactor.utils.mock import MockAnalogIn, MockI2C
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.actions.led_intensity import led_intensity, CHANNELS as LED_CHANNELS
from pioreactor.hardware_mappings import SCL, SDA
from pioreactor.pubsub import QOS


class ADCReader(BackgroundSubJob):
    """
    This job publishes the voltage reading from specified channels. Call `take_reading`
    to extract a reading.

    We publish the `first_ads_obs_time` to MQTT so other jobs can read it and
    make decisions. For example, if a bubbler is active, it should time itself
    s.t. it is _not_ running when an turbidity measurement is about to occur.

    Notes
    ------
    It's currently highly specific to the ADS1x15 family - a future code
    release may turn ADCReader into an abstract class, and classes like ADS1015Reader
    as subclasses.

    Parameters
    ------------
    channels: list
        a list of channels, a subset of [0, 1, 2, 3]
    fake_data: bool
        generate fake ADC readings internally.
    dynamic_gain: bool
        dynamically change the gain based on the max reading from channels
    initial_gain: number
        set the initial gain - see data sheet for values.

    """

    DATA_RATE = 128
    ADS_GAIN_THRESHOLDS = {
        2 / 3: (4.096, 6.144),  # 1 bit = 3mV, for 16bit ADC
        1: (2.048, 4.096),  # 1 bit = 2mV
        2: (1.024, 2.048),  # 1 bit = 1mV
        4: (0.512, 1.024),  # 1 bit = 0.5mV
        8: (0.256, 0.512),  # 1 bit = 0.25mV
        16: (-1, 0.256),  # 1 bit = 0.125mV
    }

    JOB_NAME = "adc_reader"
    published_settings = {"first_ads_obs_time": {"datatype": "float", "settable": False}}

    def __init__(
        self,
        channels,
        fake_data=False,
        dynamic_gain=True,
        initial_gain=1,
        unit=None,
        experiment=None,
        **kwargs,
    ):
        super(ADCReader, self).__init__(
            job_name=self.JOB_NAME, unit=unit, experiment=experiment, **kwargs
        )
        self.fake_data = fake_data
        self.dynamic_gain = dynamic_gain
        self.gain = initial_gain
        self._counter = 0
        self.ema = ExponentialMovingAverage(alpha=0.10)
        self.ads = None
        self.channels = channels
        self.analog_in = []

        # this is actually important to set in the init. When this job starts, setting these the "default" values
        # will clear any cache in mqtt (if a cache exists).
        self.first_ads_obs_time = None
        self.batched_readings = dict()

    def setup_adc(self):
        try:
            import adafruit_ads1x15.ads1115 as ADS

            if self.fake_data:
                i2c = MockI2C(SCL, SDA)
            else:
                import busio

                i2c = busio.I2C(SCL, SDA)

            # we may change the gain dynamically later.
            # data_rate is measured in signals-per-second, and generally has less noise the lower the value. See datasheet.
            # TODO: update this to ADS1015
            self.ads = ADS.ADS1115(i2c, data_rate=self.DATA_RATE)
            self.set_ads_gain(self.gain)
        except ValueError as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            raise e

        for channel in self.channels:
            if self.fake_data:
                ai = MockAnalogIn(self.ads, channel)
            else:
                from adafruit_ads1x15.analog_in import AnalogIn

                ai = AnalogIn(self.ads, channel)
            self.analog_in.append((channel, ai))

        # check if using correct gain
        # this may need to be adjusted for higher rates of data collection
        if self.dynamic_gain:
            max_signal = 0
            # we will instantiate and sweep through to set the gain
            for _, ai in self.analog_in:

                raw_signal_ = ai.voltage
                max_signal = max(raw_signal_, max_signal)

            self.check_on_max(max_signal)
            self.check_on_gain(max_signal)

    def check_on_max(self, value):
        if value > 3.1:
            self.logger.error(
                f"An ADC channel is recording a very high voltage, {round(value, 2)}V. We are shutting down components and jobs to keep the ADC safe."
            )
            for channel in LED_CHANNELS:
                led_intensity(
                    channel,
                    intensity=0,
                    unit=self.unit,
                    experiment=self.experiment,
                    source_of_event=self.job_name,
                    verbose=True,
                )
            try:
                # parent object, ODReading, isn't always present - sometimes we use ADCReader outside of ODReading
                self.parent.set_state("disconnected")
            except Exception:
                pass

    def check_on_gain(self, value):
        for gain, (lb, ub) in self.ADS_GAIN_THRESHOLDS.items():
            if (0.925 * lb <= value < 0.925 * ub) and (self.ads.gain != gain):
                self.gain = gain
                self.set_ads_gain(self.gain)
                self.logger.debug(f"ADC gain updated to {self.gain}.")
                break

    def set_ads_gain(self, gain):
        self.ads.gain = gain  # this assignment checks to see if the the gain is allowed.

    def on_disconnect(self):
        for attr in self.published_settings:
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.AT_LEAST_ONCE,
            )

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

        assert len(x) == len(y)
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
        AIC = n * np.log(SSE / n) + 2 * 3

        A = np.sqrt(b ** 2 + c ** 2)
        phi = np.arcsin(c / np.sqrt(b ** 2 + c ** 2))

        return (C, A, phi), AIC

    def take_reading(self):
        """
        Sample from the ADS - likely this has been optimized for use for optical density in the Pioreactor system.

        Returns
        ---------
        readings: dict
            a dict with `timestamp` of when the reading occurred, and specified channels (as ints) and their reading
            Ex: {0: 0.10240, 1: 0.1023459, 'timestamp': '2021-07-29T18:44:43.556804'}


        """
        if self.first_ads_obs_time is None:
            self.first_ads_obs_time = time.time()

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

        aggregated_signals = {channel: [] for channel in self.channels}
        timestamps = {channel: [] for channel in self.channels}
        # oversample over each channel, and we aggregate the results into a single signal.
        oversampling_count = 25

        try:
            with catchtime() as time_since_start:
                for counter in range(oversampling_count):
                    with catchtime() as time_code_took_to_run:
                        for channel, ai in self.analog_in:
                            timestamps[channel].append(time_since_start())
                            # raw_signal_ = ai.voltage

                            # TODO: delete when ADS1015 is in
                            value1115 = ai.value  # int between 0 and 32767
                            value1015 = (
                                value1115 >> 4
                            ) << 4  # int between 0 and 2047, and then blow it back up to int between 0 and 32767
                            aggregated_signals[channel].append(value1015)

                    time.sleep(
                        max(
                            0,
                            0.80 / (oversampling_count - 1)
                            - time_code_took_to_run()  # the time_code_took_to_run() reduces the variance by accounting for the duration of each sampling.
                            + 0.005
                            * (
                                (counter * 0.618034) % 1
                            ),  # this is to artificially spread out the samples, so that we observe less aliasing.
                        )
                    )

            batched_estimates_ = {}
            for channel in self.channels:

                (
                    best_estimate_of_signal_,
                    *_other_params,
                ), _ = self.sin_regression_with_known_freq(
                    timestamps[channel],
                    aggregated_signals[channel],
                    60,
                    prior_C=(
                        self.batched_readings[channel]
                        * 32767
                        / _ADS1X15_PGA_RANGE[self.ads.gain]
                    )
                    if (channel in self.batched_readings)
                    else None,
                    penalizer_C=0.5,  # TODO: this penalizer should scale with reading...
                )

                # convert to voltage
                best_estimate_of_signal_ = (
                    best_estimate_of_signal_  # TODO: delete when ADS1015 is in.
                    * _ADS1X15_PGA_RANGE[self.ads.gain]
                    / 32767
                )

                batched_estimates_[channel] = best_estimate_of_signal_

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (
                    (self._counter % 60 == 0)
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

            # publish the batch of data, too, for reading,
            # publishes to pioreactor/{self.unit}/{self.experiment}/{self.job_name}/batched_readings
            batched_estimates_["timestamp"] = current_utc_time()
            self.batched_readings = batched_estimates_

            # the max signal should determine the ADS1x15's gain
            if self.dynamic_gain:
                self.ema.update(max_signal)

            # check if using correct gain
            # this should update after first observation
            # this may need to be adjusted for higher rates of data collection
            check_gain_every_n = 5
            if (
                self.dynamic_gain
                and self._counter % check_gain_every_n == 1
                and self.ema.value is not None
            ):
                self.check_on_gain(self.ema.value)

            return batched_estimates_

        except OSError as e:
            # just skip, not sure why this happens when add_media or remove_waste are called.
            self.logger.debug(e, exc_info=True)
            self.logger.error(f"error {str(e)}. Attempting to continue.")

        except Exception as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)
            raise e


class TemperatureCompensator(BackgroundSubJob):
    """
    This class listens for changes in temperature, and will allow OD to compensate
    for the temp changes.

    Override `compensate_od_for_temperature(self, OD)` to perform the compensation.
    """

    def __init__(self, unit=None, experiment=None, **kwargs):
        super(TemperatureCompensator, self).__init__(
            job_name="temperature_compensator", unit=unit, experiment=experiment, **kwargs
        )
        self.initial_temperature = None
        self.latest_temperature = None
        self.previous_temperature = None
        self.time_of_last_temperature = None
        self.start_passive_listeners()

    def update_temperature(self, msg):
        if not msg.payload:
            return

        tmp = json.loads(msg.payload)["temperature"]

        if self.initial_temperature is None:
            self.initial_temperature = tmp

        if self.previous_temperature is None:
            self.previous_temperature = tmp
        else:
            self.previous_temperature = self.latest_temperature

        self.latest_temperature = tmp
        self.time_of_last_temperature = time.time()

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.update_temperature,
            f"pioreactor/{self.unit}/{self.experiment}/temperature_control/temperature",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )

    def compensate_od_for_temperature(self, OD):
        raise NotImplementedError


class LinearTemperatureCompensator(TemperatureCompensator):
    def __init__(self, linear_coefficient, *args, **kwargs):
        super(LinearTemperatureCompensator, self).__init__(*args, **kwargs)
        assert linear_coefficient < 0, "should be negative..."
        self.linear_coefficient = linear_coefficient

    def compensate_od_for_temperature(self, OD):
        """
        See https://github.com/Pioreactor/pioreactor/issues/143 for our analysis

        To avoid large jumps when a new temperature reading arrives,
        we interpolate between the new temp reading and the old temp reading. This should
        smooth things out.

        """

        if self.initial_temperature is None:
            return OD
        else:
            from math import exp

            time_since_last = time.time() - self.time_of_last_temperature
            f = min(time_since_last / (10 * 60), 1)  # interpolate to current temp
            iterpolated_temp = (
                f * self.latest_temperature + (1 - f) * self.previous_temperature
            )
            return OD / exp(
                self.linear_coefficient * (iterpolated_temp - self.initial_temperature)
            )


class ODReader(BackgroundJob):
    """
    Produce a stream of OD readings from the sensors.

    Parameters
    -----------

    channel_angle_map: dict
        dict of (ADS channel: label) pairs, ex: {"A0": "135/0", "A1": "90/1"}
    stop_IR_led_between_ADC_readings: bool
        bool for if the IR LED should turn off between ADC readings. Helps improve
        lifetime of LED and allows for other optics signals to occur with interference.
    adc_reader:
        Probably an ADCReader
    temperature_compensator:
        Probably a TemperatureCompensator
    """

    published_settings = {
        "led_intensity": {"datatype": "float", "settable": True},
        "interval": {"datatype": "float", "settable": False},
    }

    def __init__(
        self,
        channel_angle_map,
        interval,
        unit=None,
        experiment=None,
        stop_IR_led_between_ADC_readings=True,
        adc_reader=None,
        temperature_compensator=None,
    ):
        super(ODReader, self).__init__(
            job_name="od_reading", unit=unit, experiment=experiment
        )
        self.logger.debug(f"Starting od_reading and channels {channel_angle_map}.")

        self.adc_reader = adc_reader
        self.temperature_compensator = temperature_compensator
        self.sub_jobs = [self.adc_reader, self.temperature_compensator]

        self.channel_angle_map = channel_angle_map
        self.interval = interval

        # start IR led before ADC starts, as it needs it.
        self.led_intensity = config.getint("od_config.od_sampling", "ir_intensity")
        self.ir_channel = self.get_ir_channel_from_configuration()

        self.start_ir_led()
        self.adc_reader.setup_adc()
        self.stop_ir_led()

        self.record_from_adc_timer = RepeatedTimer(
            self.interval,
            self.record_and_publish_from_adc,
            run_immediately=True,
        ).start()

    def get_ir_channel_from_configuration(self):
        try:
            return config.get("leds_reverse", "ir_led")
        except Exception:
            self.logger.error(
                "`leds` section must contain `ir_led`. Ex: \n\n[leds]\nA=ir_led"
            )
            raise KeyError()

    def record_and_publish_from_adc(self):

        pre_duration = 0.1

        self.start_ir_led()
        time.sleep(pre_duration)
        batched_readings = self.adc_reader.take_reading()
        self.stop_ir_led()

        self.publish_single(batched_readings)
        self.publish_batch(batched_readings)

    def start_ir_led(self):
        r = led_intensity(
            self.ir_channel,
            intensity=self.led_intensity,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            verbose=False,
            pubsub_client=self.pub_client,
        )
        if not r:
            raise ValueError("IR LED could not be started. Stopping OD reading.")

        return

    def stop_ir_led(self):
        led_intensity(
            self.ir_channel,
            intensity=0,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            verbose=False,
            pubsub_client=self.pub_client,
        )

    def on_sleeping(self):
        self.record_from_adc_timer.pause()
        self.stop_ir_led()

    def on_sleeping_to_ready(self):
        self.start_ir_led()
        self.record_from_adc_timer.unpause()

    def on_disconnect(self):
        for job in self.sub_jobs:
            job.set_state("disconnected")

        # turn off the LED after we have take our last ADC reading..
        try:
            self.record_from_adc_timer.cancel()
        except Exception:
            pass
        self.stop_ir_led()

    def compensate_od_for_temperature(self, reading):
        return self.temperature_compensator.compensate_od_for_temperature(reading)

    def publish_batch(self, batched_ads_readings):
        if self.state != self.READY:
            return

        od_readings = {"od_raw": {}}
        for channel, angle in self.channel_angle_map.items():
            try:
                od_readings["od_raw"][channel] = {
                    "voltage": self.compensate_od_for_temperature(
                        batched_ads_readings[channel]
                    ),
                    "angle": angle,
                }
            except KeyError:
                self.logger.error(
                    f"Wrong channel found/not found, provided {channel}. Only valid channels are 0, 1, 2, 3."
                )
                self.set_state(self.DISCONNECTED)

        od_readings["timestamp"] = batched_ads_readings["timestamp"]
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw_batched",
            od_readings,
            qos=QOS.EXACTLY_ONCE,
        )

    def publish_single(self, batched_ads_readings):
        if self.state != self.READY:
            return

        for channel, angle in self.channel_angle_map.items():

            payload = {
                "voltage": self.compensate_od_for_temperature(
                    batched_ads_readings[channel]
                ),
                "angle": angle,
                "timestamp": batched_ads_readings["timestamp"],
            }

            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw/{channel}",
                payload,
                qos=QOS.EXACTLY_ONCE,
            )


def create_channel_angle_map(
    od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3
):
    # Inputs are either None, or a string like "135", "90,45", ...
    # Example return dict: {0: "90,135", 1: "45,135", 3:"90"}
    channel_angle_map = {}
    if od_angle_channel0:
        # TODO: we should do a check here on the values (needs to be an allowable angle) and the count (count should be the same across PDs)
        channel_angle_map[0] = od_angle_channel0

    if od_angle_channel1:
        channel_angle_map[1] = od_angle_channel1

    if od_angle_channel2:
        channel_angle_map[2] = od_angle_channel2

    if od_angle_channel3:
        channel_angle_map[3] = od_angle_channel3

    return channel_angle_map


def start_od_reading(
    od_angle_channel0,
    od_angle_channel1,
    od_angle_channel2,
    od_angle_channel3,
    sampling_rate=1 / config.getfloat("od_config.od_sampling", "samples_per_second"),
    fake_data=False,
    unit=None,
    experiment=None,
):

    unit = unit or get_unit_name()
    experiment = experiment or get_latest_experiment_name()
    channel_angle_map = create_channel_angle_map(
        od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3
    )

    return ODReader(
        channel_angle_map,
        interval=sampling_rate,
        unit=unit,
        experiment=experiment,
        adc_reader=ADCReader(
            channels=channel_angle_map.keys(),
            fake_data=fake_data,
            unit=unit,
            experiment=experiment,
        ),
        temperature_compensator=LinearTemperatureCompensator(
            -0.006380, unit=unit, experiment=experiment  # TODO: put value into config.
        ),
    )


@click.command(name="od_reading")
@click.option(
    "--od-angle-channel0",
    default=config.get("od_config.photodiode_channel", "0", fallback=None),
    type=click.STRING,
    show_default=True,
    help="specify the angle(s) between the IR LED(s) and the PD in channel 0, separated by commas. Don't specify if channel is empty.",
)
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
@click.option("--fake-data", is_flag=True, help="produce fake data (for testing)")
def click_od_reading(
    od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3, fake_data
):
    """
    Start the optical density reading job
    """
    start_od_reading(
        od_angle_channel0,
        od_angle_channel1,
        od_angle_channel2,
        od_angle_channel3,
        fake_data=fake_data or is_testing_env(),
    )
    signal.pause()
