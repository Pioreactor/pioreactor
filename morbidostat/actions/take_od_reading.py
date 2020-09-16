"""
Report the next OD reading (from start_od_reading.py) to the console.
"""
import time
import click
from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import get_unit_from_hostname

def take_od_reading(angle, verbose):
    unit = get_unit_from_hostname()

    od_topic = f"morbidostat/{unit}/od_raw/{angle}"
    try:

        result = subscribe(od_topic, keepalive=10).payload
        result = float(result)

        publish(f"morbidostat/{unit}/log", "[take_od_reading]: %.3fV" % result, verbose=verbose)
    except Exception as e:
        publish(
            f"morbidostat/{unit}/error_log",
            f"[take_od_reading]: failed with {str(e)}",
            verbose=verbose,
        )
    return result


@click.command()
@click.option("--angle", default="135", help="angle to read from")
@click.option("--verbose", is_flag=True, help="print to std out")
def click_take_od_reading(angle, verbose):
    return take_od_reading(angle, verbose)


if __name__ == "__main__":
    click_take_od_reading()
