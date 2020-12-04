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
import json
import os

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import board
import busio

from pioreactor.utils.streaming_calculations import MovingStats

from pioreactor.whoami import get_unit_from_hostname, get_latest_experiment_name
from pioreactor.config import config
from pioreactor.pubsub import publish
from pioreactor.utils.timing import every
from pioreactor.background_jobs import BackgroundJob

ADS_GAIN_THRESHOLDS = {
    2 / 3: (4.096, 6.144),
    1: (2.048, 4.096),
    2: (1.024, 2.048),
    4: (0.512, 1.024),
    8: (0.256, 0.512),
    16: (-1, 0.256),
}

JOB_NAME = os.path.splitext(os.path.basename((__file__)))[0]

unit = get_unit_from_hostname()
experiment = get_latest_experiment_name()


class ODReader(BackgroundJob):
    """
    Parameters
    -----------

    od_channels: list of (label, ADS channel), ex: [("90/A", 0), ("90/B", 1), ...]

    """

    editable_settings = []

    def __init__(self, od_channels, ads, unit=None, experiment=None, verbose=0):
        super(ODReader, self).__init__(
            job_name=JOB_NAME, verbose=verbose, unit=unit, experiment=experiment
        )
        self.ma = MovingStats(lookback=10)
        self.ads = ads
        self.od_channels_to_analog_in = {}

        for (label, channel) in od_channels:
            ai = AnalogIn(self.ads, getattr(ADS, "P" + channel))
            self.od_channels_to_analog_in[label] = ai

    def take_reading(self, counter=None):
        while self.state != self.READY:
            time.sleep(0.5)

        try:
            raw_signals = {}
            for (angle_label, ads_channel) in self.od_channels_to_analog_in.items():
                raw_signal_ = ads_channel.voltage
                publish(
                    f"pioreactor/{self.unit}/{self.experiment}/od_raw/{angle_label}",
                    raw_signal_,
                    verbose=self.verbose,
                )
                raw_signals[angle_label] = raw_signal_

                # since we don't show the user the raw voltage values, they may miss that they are near saturation of the op-amp (and could
                # also damage the ADC). We'll alert the user if the voltage gets higher than 2.5V, which is well above anything normal.
                # This is not for culture density saturation (different, harder problem)
                if (counter % 20 == 0) and (raw_signal_ > 2.5):
                    publish(
                        f"pioreactor/{self.unit}/{self.experiment}/log",
                        f"[{JOB_NAME}] OD sensor {angle_label} is recording a very high voltage, {raw_signal_}V.",
                        verbose=self.verbose,
                    )
                # TODO: check if more than 3V, and shut down something? to prevent damage to ADC.

            # publish the batch of data, too, for growth reading
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/od_raw_batched",
                json.dumps(raw_signals),
                verbose=self.verbose,
            )

            # the max signal should determine the board's gain
            self.ma.update(max(raw_signals.values()))

            # check if using correct gain
            check_gain_every_n = 10
            assert (
                check_gain_every_n >= self.ma.lookback
            ), "ma.mean won't be defined if you peek too soon"
            if counter % check_gain_every_n == 0 and self.ma.mean is not None:
                for gain, (lb, ub) in ADS_GAIN_THRESHOLDS.items():
                    if (0.95 * lb <= self.ma.mean < 0.95 * ub) and (
                        self.ads.gain != gain
                    ):
                        self.ads.gain = gain
                        publish(
                            f"pioreactor/{self.unit}/{self.experiment}/log",
                            f"[{JOB_NAME}] ADC gain updated to {self.ads.gain}.",
                            verbose=self.verbose,
                        )
                        break

            return raw_signals

        except OSError as e:
            # just pause, not sure why this happens when add_media or remove_waste are called.
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/error_log",
                f"[{JOB_NAME}] failed with {str(e)}. Attempting to continue.",
                verbose=self.verbose,
            )
            time.sleep(5.0)
        except Exception as e:
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/error_log",
                f"[{JOB_NAME}] failed with {str(e)}",
                verbose=self.verbose,
            )
            raise e


INPUT_TO_LETTER = {"0": "A", "1": "B", "2": "C", "3": "D"}


def od_reading(
    od_angle_channel,
    verbose,
    sampling_rate=1 / float(config["od_sampling"]["samples_per_second"]),
):
    od_channels = []
    for input_ in od_angle_channel:
        angle, channel = input_.split(",")

        # We split input of the form ["135,x", "135,y", "90,z"] into the form
        # "135/A", "135/B", "90/C"
        angle_label = str(angle) + "/" + INPUT_TO_LETTER[channel]

        od_channels.append((angle_label, channel))

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, gain=2)  # we will change the gain dynamically later.
    try:
        yield from every(
            sampling_rate,
            ODReader(
                od_channels, ads, unit=unit, experiment=experiment, verbose=verbose
            ).take_reading,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        publish(
            f"pioreactor/{unit}/{experiment}/error_log",
            f"[{JOB_NAME}]: failed with {e}.",
            verbose=verbose,
        )


@click.command()
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=list(config["od_config"].values()),
    type=click.STRING,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,2

""",
)
@click.option(
    "--verbose",
    "-v",
    count=True,
    help="print to std. out (may be redirected to pioreactor.log). Increasing values log more.",
)
def click_od_reading(od_angle_channel, verbose):
    reader = od_reading(od_angle_channel, verbose)
    while True:
        next(reader)


if __name__ == "__main__":
    click_od_reading()
