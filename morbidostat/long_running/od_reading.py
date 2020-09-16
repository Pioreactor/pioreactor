"""
Continuously take an optical density reading (more accurately: a backscatter reading, which is a proxy for OD).
This script is designed to run in a background process and push data to MQTT.

>>> nohup python3 -m morbidostat.long_running.od_reading &
"""
import time
import json

import click
from adafruit_ads1x15.analog_in import AnalogIn
import adafruit_ads1x15.ads1115 as ADS
import board
import busio

from morbidostat.utils.streaming_calculations import MovingStats
from morbidostat.utils import config
from morbidostat.utils.pubsub import publish


ADS_GAIN_THRESHOLDS = {
    2 / 3: (4.096, 6.144),
    1: (2.048, 4.096),
    2: (1.024, 2.048),
    4: (0.512, 1.024),
    8: (0.256, 0.512),
    16: (0.0, 0.256),
}


@click.command()
@click.argument("unit")
@click.option(
    "--od_angle_channel",
    multiple=True,
    default=["135,0"],
    type=click.STRING,
    help="""
pair of angle,channel for optical density reading. Can be invoked multiple times. Ex:

--od_angle_channel 135,0 --od_angle_channel 90,1 --od_angle_channel 45,2

""",
)
@click.option("--verbose", is_flag=True, help="print to std out")
def od_reading(unit, verbose, od_angle_channel):

    i2c = busio.I2C(board.SCL, board.SDA)
    ads = ADS.ADS1115(i2c, gain=2)  # we change the gain dynamically later

    od_channels = []
    for input_ in od_angle_channel:
        angle, channel = input_.split(",")
        od_channels.append((angle, AnalogIn(ads, getattr(ADS, "P" + channel))))

    sampling_rate = 1 / float(config["od_sampling"]["samples_per_second"])
    ma = MovingStats(lookback=20)

    publish(f"morbidostat/{unit}/log", "[od_reading]: starting", verbose=verbose)

    i = 1
    while True:
        cycle_start_time = time.time()
        try:

            raw_signals = {}
            for angle, channel in od_channels:
                raw_signal_ = channel.voltage
                publish(f"morbidostat/{unit}/od_raw/{angle}", raw_signal_, verbose=verbose)
                raw_signals[angle] = raw_signal_

            # publish the batch of data, too, for growth reading
            publish(f"morbidostat/{unit}/od_raw_batched", json.dumps(raw_signals), verbose=verbose)

            # the max signal should determine the board's gain
            ma.update(max(raw_signals.values()))
            if verbose:
                print(max(raw_signals.values()))
                print(ma.mean)

            # check if using correct gain
            if i % 100 == 0 and ma.mean is not None:
                for gain, (lb, ub) in ADS_GAIN_THRESHOLDS.items():
                    if 0.85 * lb <= ma.mean < 0.85 * ub:
                        ads.gain = gain
                        break

            i += 1

            cycle_end_time = time.time()
            delta_cycle_time = cycle_end_time - cycle_start_time

            time.sleep(max(sampling_rate - delta_cycle_time, 0))

        except OSError as e:
            # just pause, not sure why this happens when add_media or remove_waste are called.
            publish(
                f"morbidostat/{unit}/error_log",
                f"[od_reading] failed with {str(e)}. Attempting to continue.",
                verbose=verbose,
            )
            time.sleep(5.0)
        except Exception as e:
            publish(f"morbidostat/{unit}/log", f"[od_reading] failed with {str(e)}", verbose=verbose)
            publish(
                f"morbidostat/{unit}/error_log", f"[od_reading] failed with {str(e)}", verbose=verbose,
            )
            raise e


if __name__ == "__main__":
    od_reading()
