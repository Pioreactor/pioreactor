# take_optical_density

# remove waste
import time
import configparser
import click
from  paho.mqtt import subscribe, publish

TOPIC = "morbidostat/IR1_moving_average"

@click.command()
def take_optical_density():


    click.echo(click.style("starting take_optical_density", fg='green'))
    publish.single("morbidostat/log", "starting take_optical_density")

    try:
        result = float(subscribe.simple(TOPIC).payload.decode(encoding='UTF-8'))
    except e:
        print(e)
        return

    click.echo(click.style(result, fg='yellow'))
    publish.single("morbidostat/log", "take_optical_density read %s" % result)

    return



if __name__ == '__main__':
    try:
        take_optical_density()
    except Exception as e:
        print(e)