"""
Report the next OD reading (from start_od_reading.py) to the console.
"""
import time
import click
from paho.mqtt import subscribe
from morbidostat.utils.publishing import publish


def take_od_reading(unit, verbose):

    od_topic = f"morbidostat/{unit}/od_raw"
    try:

        result = subscribe.simple(od_topic, keepalive=10).payload.decode(encoding="UTF-8")
        result = float(result)

        publish(f"morbidostat/{unit}/log", "take_od_reading: %.3fV" % result, verbose=verbose)
    except Exception as e:
        publish(f"morbidostat/{unit}/error_log", f"{unit} take_od_reading.py failed with {str(e)}", verbose=verbose)
    return result


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
@click.option("--verbose", default=1, help="The morbidostat unit")
def click_take_od_reading(unit, verbose):
    return take_od_reading(unit, verbose)


if __name__ == "__main__":
    click_take_od_reading()
