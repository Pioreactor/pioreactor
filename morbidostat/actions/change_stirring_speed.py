# -*- coding: utf-8 -*-
import click

from morbidostat.whoami import unit, experiment
from morbidostat.pubsub import publish


def change_stirring_speed(duty_cycle, verbose=0):
    assert 0 <= duty_cycle <= 100

    publish(f"morbidostat/{unit}/{experiment}/stirring/duty_cycle", duty_cycle, verbose=verbose)
    return


@click.command()
@click.option("--duty-cycle", type=int)
@click.option(
    "--verbose", "-v", count=True, help="print to std. out (may be redirected to morbidostat.log). Increasing values log more."
)
def click_change_stirring_speed(duty_cycle, verbose):
    return change_stirring_speed(duty_cycle, verbose)


if __name__ == "__main__":
    click_change_stirring_speed()
