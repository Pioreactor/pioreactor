# take_optical_density

# remove waste
import time
import configparser
import click
from  paho.mqtt import subscribe, publish

TOPIC = "morbidostat/IR1_low_pass"

@click.command()
def take_optical_density():


    click.echo(click.style("starting take_optical_density", fg='green'))
    publish.single("morbidostat/log", "starting take_optical_density")

    try:
        result = subscribe.simple(TOPIC, keepalive=10).payload.decode(encoding='UTF-8')
        result = float(result)
    except Exception as e:
        click.echo(str(e))
        return

    click.echo(click.style("   %.3f" % result, fg='yellow'))
    publish.single("morbidostat/log", "take_optical_density read %.3f" % result)

    return



if __name__ == '__main__':
    try:
        take_optical_density()
    except Exception as e:
        click.echo(str(e))