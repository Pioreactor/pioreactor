# -*- coding: utf-8 -*-
"""
cmd line interface for running individual pioreactor units (including leader)

> pio run stirring
> pio run od_reading --od-angle-channel 135,0
> pio log
"""
import click
from pioreactor.whoami import am_I_leader


@click.group()
def pio():
    pass


@pio.command(name="logs", short_help="tail the logs")
def logs():
    """
    Tail the logs from /var/log/pioreactor.log to the terminal. CTRL-C to exit.
    """
    from sh import tail

    try:
        tail_sh = tail("-f", "/var/log/pioreactor.log", _iter=True)
        for line in tail_sh:
            print(line, end="")
    except KeyboardInterrupt:
        tail_sh.kill()


@pio.command(name="kill", short_help="kill job")
@click.argument("process")
def kill(process):
    """
    send SIGTERM signal to PROCESS
    """

    # TODO this fails for python
    from sh import kill, pgrep

    try:
        # remove the _oldest_ one
        kill(int(pgrep("-f", "-o", process)))
    except Exception:
        pass


@pio.group()
def run():
    pass


if am_I_leader():
    pass


# else:
from pioreactor.background_jobs.stirring import click_stirring

from pioreactor.background_jobs.growth_rate_calculating import (
    click_growth_rate_calculating,
)
from pioreactor.background_jobs.od_reading import click_od_reading
from pioreactor.background_jobs.io_controlling import click_io_controlling

run.add_command(click_growth_rate_calculating)
run.add_command(click_stirring)
run.add_command(click_od_reading)
run.add_command(click_io_controlling)
