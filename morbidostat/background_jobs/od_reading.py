# -*- coding: utf-8 -*-
"""
Continuously take an optical density reading (more accurately: a backscatter reading, which is a proxy for OD).
This script is designed to run in a background process and push data to MQTT.

>>> morbidostat od_reading --background


Topics published to

    morbidostat/<unit>/<experiment>/od_raw/<angle>/<label>

Ex:

    morbidostat/1/trial15/od_raw/135/A


Also published to

    morbidostat/<unit>/<experiment>/od_raw_batched



"""
import time
import json
import string
from collections import Counter

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import board
import busio

from morbidostat.utils.streaming_calculations import MovingStats
from morbidostat.utils import log_start, log_stop
from morbidostat.whoami import unit, experiment
from morbidostat.config import config
from morbidostat.pubsub import publish
from morbidostat.utils.timing import every


ADS_GAIN_THRESHOLDS = {
    2 / 3: (4.096, 6.144),
    1: (2.048, 4.096),
    2: (1.024, 2.048),
    4: (0.512, 1.024),
    8: (0.256, 0.512),
    16: (-1, 0.256),
}


@log_start(unit, experiment)
@log_stop(unit, experiment)
def od_reading(verbose, od_angle_channel):

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, gain=2)  # we change the gain dynamically later

    angle_counter = Counter()
    od_channels = []
    for input_ in od_angle_channel:
        angle, channel = input_.split(",")

        # We split input of the form ["135,x", "135,y", "90,z"] into the form
        # "135/A", "135/B", "90/A"
        angle_counter.update([angle])
        angle_label = str(angle) + "/" + string.ascii_uppercase[angle_counter[angle] - 1]

        ai = AnalogIn(ads, getattr(ADS, "P" + channel))
        od_channels.append((angle_label, ai))

    sampling_rate = 1 / float(config["od_sampling"]["samples_per_second"])
    ma = MovingStats(lookback=20)

    def take_reading(counter=None):
        try:
            raw_signals = {}
            for (angle_label, channel) in od_channels:
                raw_signal_ = channel.voltage
                publish(f"morbidostat/{unit}/{experiment}/od_raw/{angle_label}", raw_signal_, verbose=verbose)
                raw_signals[angle_label] = raw_signal_

            # publish the batch of data, too, for growth reading
            publish(f"morbidostat/{unit}/{experiment}/od_raw_batched", json.dumps(raw_signals), verbose=verbose)

            # the max signal should determine the board's gain
            ma.update(max(raw_signals.values()))

            # check if using correct gain
            if counter % 20 == 0 and ma.mean is not None:
                for gain, (lb, ub) in ADS_GAIN_THRESHOLDS.items():
                    if 0.85 * lb <= ma.mean < 0.85 * ub:
                        ads.gain = gain
                        break
        except OSError as e:
            # just pause, not sure why this happens when add_media or remove_waste are called.
            publish(
                f"morbidostat/{unit}/{experiment}/error_log",
                f"[od_reading] failed with {str(e)}. Attempting to continue.",
                verbose=verbose,
            )
            time.sleep(5.0)
        except Exception as e:
            publish(f"morbidostat/{unit}/{experiment}/error_log", f"[od_reading] failed with {str(e)}", verbose=verbose)
            raise e

    yield from every(sampling_rate, take_reading)


@click.command()
@click.option(
    "--od-angle-channel",
    multiple=True,
    default=["135,0"],
    type=click.STRING,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od-angle-channel 135,0 --od-angle-channel 90,1 --od-angle-channel 45,2

""",
)
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_od_reading(verbose, od_angle_channel):
    reader = od_reading(verbose, od_angle_channel)
    while True:
        next(reader)


if __name__ == "__main__":
    click_od_reading()
