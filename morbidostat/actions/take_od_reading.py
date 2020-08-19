"""
Report the next OD reading (from start_od_reading.py) to the console.
"""
import time
import click
from  paho.mqtt import subscribe, publish



def take_od_reading(unit):

    od_topic = f"morbidostat/{unit}/od_low_pass"
    try:

        click.echo(click.style("starting take_od_reading", fg='green'))

        result = subscribe.simple(od_topic, keepalive=10).payload.decode(encoding='UTF-8')
        result = float(result)

        click.echo(click.style("   %.3f" % result, fg='yellow'))
        publish.single(f"morbidostat/{unit}/log", "take_od_reading: %.3fV" % result)
    except Exception as e:
        publish.single(f"morbidostat/{unit}/error_log", f"{unit} take_od_reading.py failed with {str(e)}")
    return result


@click.command()
@click.option('--unit', default="1", help='The morbidostat unit')
def click_take_od_reading(unit):
    return take_od_reading(unit)


if __name__ == '__main__':
    click_take_od_reading()
