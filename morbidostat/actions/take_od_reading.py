"""
Report the next OD reading (from start_od_reading.py) to the console.
"""
import time
import click
from  paho.mqtt import subscribe, publish


@click.command()
def take_optical_density():

    morbidostat = "morbidostat1"


    od_topic = f"{morbidostat}/od_low_pass"

    click.echo(click.style("starting take_optical_density", fg='green'))

    try:
        result = subscribe.simple(od_topic, keepalive=10).payload.decode(encoding='UTF-8')
        result = float(result)
    except Exception as e:
        click.echo(str(e))
        return

    click.echo(click.style("   %.3f" % result, fg='yellow'))
    publish.single(f"{morbidostat}/log", "take_optical_density: %.3fV" % result)

    return



if __name__ == '__main__':
    try:
        take_optical_density()
    except Exception as e:
        click.echo(str(e))