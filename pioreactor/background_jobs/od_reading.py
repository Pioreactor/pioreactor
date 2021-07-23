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


Internally, the subjob ADCReader reads all channels from the ADC and pushes to MQTT. The ODReader listens to
these MQTT topics, and re-publishes only the data that represents optical densities. Why do it this way? In
the future, there could be other photodiodes / analog signals that plug into the ADS, and they listen (and republish)
in the same manner.

In the ADCReader class, we publish the `first_ads_obs_time` to MQTT so other jobs can read it and
make decisions. For example, if a bubbler/visible light LED is active, it should time itself
s.t. it is _not_ running when an turbidity measurement is about to occur. `interval` is there so
that it's clear the duration between readings, and in case the config.ini is changed between this job
starting and the downstream job starting. It takes about 0.5-0.6 seconds to read (and publish) *all
the channels. This can be shortened by changing the data_rate in the config to a higher value.

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
from pioreactor.pubsub import QOS, subscribe


class ADCReader(BackgroundSubJob):
    """
    This job publishes the voltage reading from _all_ channels, and downstream
    jobs can selectively choose a channel to listen to. We don't publish until
    `start_periodic_reading()` is called, otherwise, call `take_reading` manually.
    The read values are stored in A0, A1, A2, and A3.

    We publish the `first_ads_obs_time` to MQTT so other jobs can read it and
    make decisions. For example, if a bubbler is active, it should time itself
    s.t. it is _not_ running when an turbidity measurement is about to occur.
    `interval` is there so that it's clear the duration between readings,
    and in case the config.ini is changed between this job starting and the downstream
    job starting.

    """

    ADS_GAIN_THRESHOLDS = {
        2 / 3: (4.096, 6.144),  # 1 bit = 3mV (default)
        1: (2.048, 4.096),  # 1 bit = 2mV
        2: (1.024, 2.048),  # 1 bit = 1mV
        4: (0.512, 1.024),  # 1 bit = 0.5mV
        8: (0.256, 0.512),  # 1 bit = 0.25mV
        16: (-1, 0.256),  # 1 bit = 0.125mV
    }

    JOB_NAME = "adc_reader"
    editable_settings = [
        "interval",
        "first_ads_obs_time",
        "A0",
        "A1",
        "A2",
        "A3",
        "batched_readings",
    ]

    def __init__(
        self,
        interval=None,
        fake_data=False,
        unit=None,
        experiment=None,
        dynamic_gain=True,
        initial_gain=1,
        **kwargs,
    ):
        super(ADCReader, self).__init__(
            job_name=self.JOB_NAME, unit=unit, experiment=experiment, **kwargs
        )
        self.fake_data = fake_data
        self.interval = interval
        self.dynamic_gain = dynamic_gain
        self.initial_gain = initial_gain
        self.counter = 0
        self.ema = ExponentialMovingAverage(alpha=0.10)
        self.ads = None
        self.analog_in = []

        self.data_rate = config.getint("od_config.od_sampling", "data_rate")

        # this is actually important to set in the init. When this job starts, setting these the "default" values
        # will clear any cache in mqtt (if a cache exists).
        self.first_ads_obs_time = None
        self.timer = None
        self.A0 = None
        self.A1 = None
        self.A2 = None
        self.A3 = None
        self.batched_readings = dict()

        self.setup_adc()

        if self.interval:
            self.timer = RepeatedTimer(
                self.interval, self.take_reading, run_immediately=True
            )

    def start_periodic_reading(self):
        # start publishing every `interval` seconds.
        if self.timer:
            self.timer.start()

    def setup_adc(self):
        if self.fake_data:
            i2c = MockI2C(SCL, SDA)
        else:
            import busio

            i2c = busio.I2C(SCL, SDA)

        try:
            import adafruit_ads1x15.ads1115 as ADS

            # we will change the gain dynamically later.
            # data_rate is measured in signals-per-second, and generally has less noise the lower the value. See datasheet.
            # TODO: update this to ADS1015
            self.ads = ADS.ADS1115(i2c, gain=self.initial_gain, data_rate=self.data_rate)
        except ValueError as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            raise e

        for channel in [0, 1, 2, 3]:
            if self.fake_data:
                ai = MockAnalogIn(self.ads, getattr(ADS, f"P{channel}"))
            else:
                from adafruit_ads1x15.analog_in import AnalogIn

                ai = AnalogIn(self.ads, getattr(ADS, f"P{channel}"))
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
                self.ads.gain = gain
                self.logger.debug(f"ADC gain updated to {self.ads.gain}.")
                break

    def on_disconnect(self):
        for attr in self.editable_settings:
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                retain=True,
                qos=QOS.AT_LEAST_ONCE,
            )

        try:
            self.timer.cancel()
        except AttributeError:
            pass

    def sin_regression_with_known_freq(self, x, y, freq):
        """
        Assumes a known frequency...

        Reference
        ------------
        https://scikit-guess.readthedocs.io/en/latest/appendices/reei/translation.html#further-optimizations-based-on-estimates-of-a-and-rho


        """
        import numpy as np

        assert len(x) == len(y)
        x = np.asarray(x)
        y = np.asarray(y)
        n = x.shape[0]

        sin_x = np.sin(freq * x)
        cos_x = np.cos(freq * x)

        sum_sin = sin_x.sum()
        sum_cos = cos_x.sum()
        sum_sin2 = (sin_x ** 2).sum()
        sum_cos2 = (cos_x ** 2).sum()
        sum_cossin = (cos_x * sin_x).sum()

        sum_y = y.sum()
        sum_ysin = (y * sin_x).sum()
        sum_ycos = (y * cos_x).sum()

        M = np.array(
            [
                [n, sum_sin, sum_cos],
                [sum_sin, sum_sin2, sum_cossin],
                [sum_cos, sum_cossin, sum_cos2],
            ]
        )
        Y = np.array([sum_y, sum_ysin, sum_ycos])

        try:
            a, b, c = np.linalg.solve(M, Y)
        except np.linalg.LinAlgError:
            self.logger.error("error in regression")
            self.logger.debug(M)
            self.logger.debug(x)
            self.logger.debug(y)
            return y.mean()

        # return a, np.sqrt(b**2 + c**2), np.arcsin(c/np.sqrt(b**2 + c**2))
        return a

    def take_reading(self):

        if self.first_ads_obs_time is None:
            self.first_ads_obs_time = time.time()

        self.counter += 1

        _ADS1X15_PGA_RANGE = {  # TODO: delete when ads1015 is in.
            2 / 3: 6.144,
            1: 4.096,
            2: 2.048,
            4: 1.024,
            8: 0.512,
            16: 0.256,
        }
        max_signal = 0

        aggregated_signals = {"A0": [], "A1": [], "A2": [], "A3": []}
        timestamps = {"A0": [], "A1": [], "A2": [], "A3": []}
        # oversample over each channel, and we aggregate the results into a single signal.
        oversampling_count = 25

        try:
            with catchtime() as time_since_start:
                for counter in range(oversampling_count):
                    with catchtime() as time_code_took_to_run:
                        for channel, ai in self.analog_in[0:1]:
                            timestamps[f"A{channel}"].append(time_since_start())
                            # raw_signal_ = ai.voltage
                            # aggregated_signals[f"A{channel}"] += (
                            #    raw_signal_ / oversampling_count
                            # )
                            # TODO: delete when ADS1015 is in
                            value1115 = ai.value  # int between 0 and 32767
                            value1015 = (
                                value1115 >> 4
                            ) << 4  # int between 0 and 2047, and then blow it back up to int between 0 and 32767
                            aggregated_signals[f"A{channel}"].append(value1015)
                            print(f"{value1015},")

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
                    print()

            batched_estimates_ = {}
            for channel, _ in self.analog_in[0:1]:

                best_estimate_of_signal_ = self.sin_regression_with_known_freq(
                    timestamps[f"A{channel}"],
                    aggregated_signals[f"A{channel}"],
                    2 * 3.14159 * 60,
                )

                # convert to voltage
                best_estimate_of_signal_ = (
                    best_estimate_of_signal_  # TODO: delete with ADS1015 is in.
                    * _ADS1X15_PGA_RANGE[self.ads.gain]
                    / 32767
                )

                batched_estimates_[f"A{channel}"] = best_estimate_of_signal_

                # the below will publish to pioreactor/{self.unit}/{self.experiment}/{self.job_name}/A{channel}
                setattr(
                    self,
                    f"A{channel}",
                    {
                        "voltage": best_estimate_of_signal_,
                        "timestamp": current_utc_time(),
                    },
                )

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (
                    (self.counter % 60 == 0)
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
                and self.counter % check_gain_every_n == 1
                and self.ema.value is not None
            ):
                self.check_on_gain(self.ema.value)

            return aggregated_signals

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
    """

    def __init__(self, unit, experiment):
        super(TemperatureCompensator, self).__init__(
            job_name="temperature_compensator", unit=unit, experiment=experiment
        )
        self.initial_temperature = None
        self.latest_temperature = None
        self.start_passive_listeners()

    def compensate_od_for_temperature(self, OD):
        # see https://github.com/Pioreactor/pioreactor/issues/143

        if self.initial_temperature is None:
            return OD
        else:
            from math import exp

            return OD / exp(
                -0.006380 * (self.latest_temperature - self.initial_temperature)
            )

    def update_temperature(self, msg):
        if not msg.payload:
            return

        tmp = json.loads(msg.payload)["temperature"]

        if self.initial_temperature is None:
            self.initial_temperature = tmp

        self.latest_temperature = tmp

    def start_passive_listeners(self):
        self.subscribe_and_callback(
            self.update_temperature,
            f"pioreactor/{self.unit}/{self.experiment}/temperature_control/temperature",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
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
    fake_data: bool
        Use a simulated dataset
    """

    editable_settings = ["led_intensity"]

    def __init__(
        self,
        channel_angle_map,
        sampling_rate=1,
        fake_data=False,
        unit=None,
        experiment=None,
        stop_IR_led_between_ADC_readings=True,
    ):
        super(ODReader, self).__init__(
            job_name="od_reading", unit=unit, experiment=experiment
        )
        self.logger.debug(
            f"Starting od_reading with sampling_rate {sampling_rate}s and channels {channel_angle_map}."
        )
        self.channel_angle_map = channel_angle_map
        self.fake_data = fake_data

        # start IR led before ADC starts, as it needs it.
        self.led_intensity = config.getint("od_config.od_sampling", "ir_intensity")
        self.ir_channel = self.get_ir_channel_from_configuration()

        self.start_ir_led()

        self.adc_reader = ADCReader(
            interval=sampling_rate,
            fake_data=fake_data,
            unit=self.unit,
            experiment=self.experiment,
            parent=self,
        )
        self.temperature_compensator = TemperatureCompensator(
            unit=self.unit, experiment=self.experiment
        )
        self.sub_jobs = [self.adc_reader, self.temperature_compensator]

        # start reading from the ADC
        self.adc_reader.start_periodic_reading()

        if stop_IR_led_between_ADC_readings:
            self.set_IR_led_during_ADC_readings()

        self.start_passive_listeners()

    def get_ir_channel_from_configuration(self):
        try:
            return config.get("leds_reverse", "ir_led")
        except Exception:
            self.logger.error(
                "`leds` section must contain `ir_led`. Ex: \n\n[leds]\nA=ir_led"
            )
            raise KeyError()

    def set_IR_led_during_ADC_readings(self):
        """
        This supposes IR LED is always on, and the "sneak in" turns it off. We also should turn off all other LEDs
        when we turn the IR LED on.

        post_duration: how long to wait (seconds) after the start of ADCReader.take_reading before running sneak_in
        pre_duration: duration between stopping the action and the next ADCReader reading
        """

        post_duration = 0.95
        pre_duration = 0.1

        def sneak_in():
            with catchtime() as delta_to_stop:
                # the time delta produced by the stop_ir_led can be significant, hence we
                # must account for it.
                self.stop_ir_led()

            time.sleep(
                max(0, ads_interval - (post_duration + pre_duration + delta_to_stop()))
            )
            self.start_ir_led()

        msg = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/adc_reader/first_ads_obs_time",
            timeout=20,
        )
        ads_start_time = float(msg.payload) if msg and msg.payload else 0
        msg = subscribe(
            f"pioreactor/{self.unit}/{self.experiment}/adc_reader/interval", timeout=20
        )

        ads_interval = float(msg.payload) if msg and msg.payload else 0

        if ads_interval < 1.5:
            # if this is too small, like 1.5s, we should just skip this whole thing and keep the IR LED always on.
            return

        time_to_next_ads_reading = ads_interval - (
            (time.time() - ads_start_time) % ads_interval
        )

        self.sneak_in_timer = RepeatedTimer(
            ads_interval,
            sneak_in,
            run_immediately=False,
            run_after=(time_to_next_ads_reading + post_duration),
        ).start()

    def start_ir_led(self):
        r = led_intensity(
            self.ir_channel,
            intensity=self.led_intensity,
            unit=self.unit,
            experiment=self.experiment,
            source_of_event=self.job_name,
            verbose=False,
            mock=self.fake_data,
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
            mock=self.fake_data,
            pubsub_client=self.pub_client,
        )

    def on_sleeping(self):
        self.sneak_in_timer.pause()
        self.stop_ir_led()

    def on_sleeping_to_ready(self):
        self.start_ir_led()
        self.sneak_in_timer.unpause()

    def on_disconnect(self):
        for job in self.sub_jobs:
            job.set_state("disconnected")

        # turn off the LED after we have take our last ADC reading..
        try:
            self.sneak_in_timer.cancel()
        except Exception:
            pass
        self.stop_ir_led()

    def compensate_od_for_temperature(self, reading):
        return self.temperature_compensator.compensate_od_for_temperature(reading)

    def publish_batch(self, message):
        if self.state != self.READY:
            return

        ads_readings = json.loads(message.payload)
        od_readings = {"od_raw": {}}
        for channel, angle in self.channel_angle_map.items():
            try:
                od_readings["od_raw"][channel.lstrip("A")] = {
                    "voltage": self.compensate_od_for_temperature(ads_readings[channel]),
                    "angle": angle,
                }
            except KeyError:
                self.logger.error(
                    f"Input wrong channel, provided {channel}. Only valid channels are 0, 1, 2, 3."
                )
                self.set_state(self.DISCONNECTED)

        od_readings["timestamp"] = ads_readings["timestamp"]
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw_batched",
            json.dumps(od_readings),
            qos=QOS.EXACTLY_ONCE,
        )

    def publish_single(self, message):
        if self.state != self.READY:
            return

        channel = message.topic.rsplit("/", maxsplit=1)[1]
        payload = json.loads(message.payload)
        payload["angle"] = self.channel_angle_map[channel]
        payload["voltage"] = self.compensate_od_for_temperature(payload["voltage"])
        topic_suffix = channel.lstrip("A")

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/od_raw/{topic_suffix}",
            payload,
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self):

        # process incoming data
        # allow_retained is False because we don't want to process (stale) retained ADS values
        self.subscribe_and_callback(
            self.publish_batch,
            f"pioreactor/{self.unit}/{self.experiment}/{ADCReader.JOB_NAME}/batched_readings",
            qos=QOS.EXACTLY_ONCE,
            allow_retained=False,
        )
        for channel in self.channel_angle_map:
            self.subscribe_and_callback(
                self.publish_single,
                f"pioreactor/{self.unit}/{self.experiment}/{ADCReader.JOB_NAME}/{channel}",
                qos=QOS.EXACTLY_ONCE,
                allow_retained=False,
            )


def create_channel_angle_map(
    od_angle_channel0, od_angle_channel1, od_angle_channel2, od_angle_channel3
):
    # Inputs are either None, or a string like "135", "90,45", ...
    # Example return dict: {"A0": "90,135/0", "A1": "45,135/1", "A3":"90/3"}
    channel_angle_map = {}
    if od_angle_channel0:
        # TODO: we should do a check here on the values (needs to be an allowable angle) and the count (count should be the same across PDs)
        channel_angle_map["A0"] = od_angle_channel0

    if od_angle_channel1:
        channel_angle_map["A1"] = od_angle_channel1

    if od_angle_channel2:
        channel_angle_map["A2"] = od_angle_channel2

    if od_angle_channel3:
        channel_angle_map["A3"] = od_angle_channel3

    return channel_angle_map


def od_reading(
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

    ODReader(
        channel_angle_map,
        sampling_rate=sampling_rate,
        unit=unit,
        experiment=experiment,
        fake_data=fake_data,
    )

    signal.pause()


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
    od_reading(
        od_angle_channel0,
        od_angle_channel1,
        od_angle_channel2,
        od_angle_channel3,
        fake_data=fake_data or is_testing_env(),
    )
