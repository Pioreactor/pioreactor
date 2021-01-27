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

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import busio

from pioreactor.utils.streaming_calculations import MovingStats

from pioreactor.whoami import get_unit_name, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.utils.timing import every
from pioreactor.utils.mock import MockAnalogIn, MockI2C
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.actions.leds import led_intensity

ADS_GAIN_THRESHOLDS = {
    2 / 3: (4.096, 6.144),
    1: (2.048, 4.096),
    2: (1.024, 2.048),
    4: (0.512, 1.024),
    8: (0.256, 0.512),
    16: (-1, 0.256),
}

SCL, SDA = 3, 2
JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]


class ODReader(BackgroundJob):
    """
    Produce a stream of OD readings from the sensors.

    Parameters
    -----------

    od_channels: list of (label, ADS channel), ex: [("90/A", 0), ("90/B", 1), ...]
    ads: ADS.ADS1x15

    """

    editable_settings = []

    def __init__(self, od_channels, unit=None, experiment=None, fake_data=False):
        super(ODReader, self).__init__(
            job_name=JOB_NAME, unit=unit, experiment=experiment
        )
        self.ma = MovingStats(lookback=10)
        self.start_ir_led()

        if fake_data:
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
        self.od_channels_to_analog_in = {}

        for (label, channel) in od_channels:
            if fake_data:
                ai = MockAnalogIn(self.ads, getattr(ADS, "P" + channel))
            else:
                ai = AnalogIn(self.ads, getattr(ADS, "P" + channel))
            self.od_channels_to_analog_in[label] = ai

    def start_ir_led(self):
        ir_channel = config.get("leds", "ir_led")
        r = led_intensity(
            ir_channel, intensity=100, unit=self.unit, experiment=self.experiment
        )
        if not r:
            raise ValueError("IR LED could not be started. Stopping OD reading.")

    def stop_ir_led(self):
        ir_channel = config.get("leds", "ir_led")
        led_intensity(ir_channel, intensity=0, unit=self.unit, experiment=self.experiment)

    def on_disconnect(self):
        self.stop_ir_led()

    def take_reading(self, counter=None):
        while self.state != self.READY:
            time.sleep(0.5)

        try:
            raw_signals = {}
            for (angle_label, ads_channel) in self.od_channels_to_analog_in.items():
                raw_signal_ = ads_channel.voltage
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/od_raw/{angle_label}",
                    raw_signal_,
                )
                raw_signals[angle_label] = raw_signal_

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than 2.5V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (counter % 20 == 0) and (raw_signal_ > 2.5):
                    self.logger.warning(
                        f"OD sensor {angle_label} is recording a very high voltage, {round(raw_signal_, 2)}V."
                    )
                # TODO: check if more than 3V, and shut down something? to prevent damage to ADC.

            # publish the batch of data, too, for growth reading
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
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


INPUT_TO_LETTER = {"0": "A", "1": "B", "2": "C", "3": "D"}


def od_reading(
    od_angle_channel,
    sampling_rate=1 / float(config["od_config.od_sampling"]["samples_per_second"]),
    fake_data=False,
):

    unit = get_unit_name()
    experiment = get_latest_experiment_name()

    od_channels = []
    for input_ in od_angle_channel:
        angle, channel = input_.split(",")

        # We split input of the form ["135,x", "135,y", "90,z"] into the form
        # "135/A", "135/B", "90/C"
        angle_label = str(angle) + "/" + INPUT_TO_LETTER[channel]
        od_channels.append((angle_label, channel))

    try:
        yield from every(
            sampling_rate,
            ODReader(
                od_channels, unit=unit, experiment=experiment, fake_data=fake_data
            ).take_reading,
        )
    except Exception as e:
        logger = logging.getLogger(JOB_NAME)
        logger.error(f"{str(e)}")
        raise e


@click.command(name="od_reading")
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=config.get("od_config.sensor_to_adc_pin", "od_angle_channel").split("|"),
    type=click.STRING,
    show_default=True,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,2

""",
)
@click.option("--fake-data", is_flag=True, help="produce fake data (for testing)")
def click_od_reading(od_angle_channel, fake_data):
    """
    Start the optical density reading job
    """
    reader = od_reading(od_angle_channel, fake_data=fake_data)
    while True:
        next(reader)
