# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a backscatter reading, which is a proxy for OD).
This script is designed to run in a background process and push data to MQTT.

>>> pioreactor od_reading --background


Topics published to

    pioreactor/<unit>/<experiment>/od_raw/<angle>/<label>

Ex:

    pioreactor/1/trial15/od_raw/135/A


Also published to

    pioreactor/<unit>/<experiment>/od_raw_batched

"""
import time
import logging
import json
import os
import signal

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import busio

from pioreactor.utils.streaming_calculations import MovingStats

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.utils.mock import MockAnalogIn, MockI2C
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.background_jobs.subjobs.base import BackgroundSubJob
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.hardware_mappings import SCL, SDA
from pioreactor.pubsub import QOS, subscribe_and_callback

ADS_GAIN_THRESHOLDS = {
    2 / 3: (4.096, 6.144),
    1: (2.048, 4.096),
    2: (1.024, 2.048),
    4: (0.512, 1.024),
    8: (0.256, 0.512),
    16: (-1, 0.256),
}

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class ADSReader(BackgroundSubJob):
    def __init__(self, sampling_rate=1, fake_data=False, unit=None, experiment=None):
        super(ADSReader, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )
        self.fake_data = fake_data
        self.ma = MovingStats(lookback=10)
        self.timer = RepeatedTimer(sampling_rate, self.take_reading)

        if self.fake_data:
            i2c = MockI2C(SCL, SDA)
        else:
            try:
                i2c = busio.I2C(SCL, SDA)
            except Exception as e:
                self.logger.error(
                    "Unable to find I2C for OD measurements. Is the Pioreactor hardware installed? Check the connections."
                )
                raise e

        # we will change the gain dynamically later.
        # data_rate is measured in signals-per-second, and generally has less noise the lower the value. See datasheet.
        self.ads = ADS.ADS1115(i2c, gain=2, data_rate=8)
        self.analog_in = []

        for channel in [0, 1, 2, 3]:
            if self.fake_data:
                ai = MockAnalogIn(self.ads, getattr(ADS, "P" + channel))
            else:
                ai = AnalogIn(self.ads, getattr(ADS, "P" + channel))
            self.analog_in.append((channel, ai))

    def on_disconnect(self):
        try:
            self.timer_thread.cancel()
        except AttributeError:
            pass

    def take_reading(self, counter=None):
        try:
            raw_signals = {}
            for channel, ai in self.analog_in:
                raw_signal_ = ai.voltage
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/ads/{channel}", raw_signal_
                )
                raw_signals[channel] = raw_signal_

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than 2.5V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (counter % 20 == 0) and (raw_signal_ > 2.5):
                    self.logger.warning(
                        f"ADS sensor {channel} is recording a very high voltage, {round(raw_signal_, 2)}V. It's recommended to keep it less than 3.3V."
                    )
                # TODO: check if more than 3V, and shut down something? to prevent damage to ADC.

            # publish the batch of data, too, for reading
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/ads_batched",
                json.dumps(raw_signals),
            )

            # the max signal should determine the board's gain
            self.ma.update(max(raw_signals.values()))

            # check if using correct gain
            check_gain_every_n = 10
            assert (
                check_gain_every_n >= self.ma._lookback
            ), "ma.mean won't be defined if you peek too soon"
            if counter % check_gain_every_n == 0 and self.ma.mean is not None:
                for gain, (lb, ub) in ADS_GAIN_THRESHOLDS.items():
                    if (0.95 * lb <= self.ma.mean < 0.95 * ub) and (
                        self.ads.gain != gain
                    ):
                        self.ads.gain = gain
                        self.logger.debug(f"ADC gain updated to {self.ads.gain}.")
                        break

            return raw_signals

        except OSError as e:
            # just pause, not sure why this happens when add_media or remove_waste are called.
            self.logger.error(f"error {str(e)}. Attempting to continue.")
            time.sleep(5.0)
        except Exception as e:
            self.logger.error(f"failed with {str(e)}")
            raise e


class ODReader(BackgroundJob):
    """
    Produce a stream of OD readings from the sensors.

    Parameters
    -----------

    channel_label_map: dict of (ADS channel: label) pairs, ex: {0: "135/0", 1: "90/1"}

    """

    editable_settings = []

    def __init__(
        self,
        channel_label_map,
        sampling_rate=1,
        fake_data=False,
        unit=None,
        experiment=None,
    ):
        super(ODReader, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )
        self.channel_label_map = channel_label_map
        self.ads_reader = ADSReader(
            sampling_rate=sampling_rate,
            fake_data=fake_data,
            unit=self.unit,
            experiment=self.experiment,
        )
        self.sub_jobs = [self.ads_reader]
        self.start_ir_led()
        self.start_passive_listeners()

    def start_ir_led(self):
        ir_channel = config.get("leds", "ir_led")
        r = led_intensity(
            ir_channel,
            intensity=100,
            source_of_event=self.job_name,
            unit=self.unit,
            experiment=self.experiment,
        )
        if not r:
            raise ValueError("IR LED could not be started. Stopping OD reading.")
        time.sleep(0.25)  # give it a moment to get to set value
        return

    def stop_ir_led(self):
        if self.fake_data:
            return
        ir_channel = config.get("leds", "ir_led")
        led_intensity(ir_channel, intensity=0, unit=self.unit, experiment=self.experiment)

    def on_disconnect(self):
        self.stop_ir_led()
        for job in self.sub_jobs:
            job.set_state("disconnected")

    def publish_batch(self, message):
        if self.state != self.READY:
            return
        ads_readings = json.loads(message.payload)
        od_readings = {}
        for channel, label in self.channel_label_map.items():
            od_readings[label] = ads_readings[channel]

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
            od_readings,
            qos=QOS.EXACTLY_ONCE,
        )

    def publish_single(self, message):
        if self.state != self.READY:
            return

        channel = int(message.topic.split("/")[0])
        if channel not in self.channel_label_map:
            return

        label = self.channel_label_map[channel]

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/od_raw/{label}",
            message.payload,
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self):

        # process incoming data
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.publish_batch,
                f"pioreactor/{self.unit}/{self.experiment}/ads/batched",
                qos=QOS.EXACTLY_ONCE,
                job_name=self.job_name,
            )
        )
        self.pubsub_clients.append(
            subscribe_and_callback(
                self.publish_single,
                f"pioreactor/{self.unit}/{self.experiment}/ads/+",
                qos=QOS.EXACTLY_ONCE,
                job_name=self.job_name,
            )
        )


def od_reading(
    od_angle_channel,
    sampling_rate=1 / float(config["od_config.od_sampling"]["samples_per_second"]),
    fake_data=False,
):

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    channel_label_map = []
    for input_ in od_angle_channel:
        angle, channel = input_.split(",")

        # We split input of the form ["135,0", "135,1", "90,3"] into the form
        # "135/0", "135/1", "90/3"
        angle_label = f"{angle}/{channel}"
        channel_label_map[int(channel)] = angle_label

    ODReader(
        channel_label_map,
        sampling_rate=sampling_rate,
        unit=unit,
        experiment=experiment,
        fake_data=fake_data,
    )

    signal.pause()


@click.command(name="od_reading")
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=config.get("od_config.photodiode_channel", "od_angle_channel").split("|"),
    type=click.STRING,
    show_default=True,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,3

""",
)
@click.option("--fake-data", is_flag=True, help="produce fake data (for testing)")
def click_od_reading(od_angle_channel, fake_data):
    """
    Start the optical density reading job
    """
    try:
        od_reading(od_angle_channel, fake_data=fake_data)
    except Exception as e:
        logger = logging.getLogger(JOB_NAME)
        logger.error(e)
        raise e
