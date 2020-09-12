"""
Report the next OD reading (from start_od_reading.py) to the console.
"""
import time
import click
from paho.mqtt import subscribe
from morbidostat.utils.publishing import publish
from morbidostat.utils import leader_hostname


def take_od_reading(unit, angle, verbose):

    od_topic = f"morbidostat/{unit}/od_raw/{angle}"
    try:

        result = subscribe.simple(od_topic, keepalive=10, hostname=leader_hostname).payload
        result = float(result)

        publish(f"morbidostat/{unit}/log", "take_od_reading: %.3fV" % result, verbose=verbose)
    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log",
            f"{unit} take_od_reading.py failed with {str(e)}",
            verbose=verbose,
        )
    return result


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--angle", default="135", help="angle to read from")
@click.option("--verbose", is_flag=True, help="print to std out")
def click_take_od_reading(unit, angle, verbose):
    return take_od_reading(unit, angle, verbose)


if __name__ == "__main__":
    click_take_od_reading()
