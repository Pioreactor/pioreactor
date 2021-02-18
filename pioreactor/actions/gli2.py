# -*- coding: utf-8 -*-

from math import sqrt
import click

from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.config import config
from pioreactor.utils import pio_jobs_running
from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT


def gli2(pd_X, pd_Y, led_X, led_Y, unit=None, experiment=None):
    """
    Advisable that stirring is turned on. OD reading should be turned off.

    The pd_Z and led_Z are the channels on the Pioreactor HAT.
    They map to the pairs of pockets at 180° angles in the Pioreactor, see below



               pd_Y
           , - ~ ~ ~ - ,
      x, '               ' ,x
     ,                       ,
    ,                         ,
   ,                           ,
 led_X                        pd_X
   ,                           ,
    ,                         ,
     ,                       ,
      x,                  , 'x
         ' - , _ _ _ ,  '
               led_Y

    """
    assert "od_reading" not in pio_jobs_running(), "Turn off od_reading job first."

    adc = ADCReader(unit=unit, experiment=experiment, dynamic_gain=False)
    adc.setup_adc()

    # reset all to 0
    led_intensity(led_X, intensity=0, verbose=False, source_of_event="gli2")
    led_intensity(led_Y, intensity=0, verbose=False, source_of_event="gli2")

    # take baseline measurements
    adc.take_reading()
    baselineX = getattr(adc, f"A{pd_X}")
    baselineY = getattr(adc, f"A{pd_Y}")

    # find values of LED intensity s.t. we don't overload the 180 degree sensor
    # X first
    for i in range(1, 100):
        led_intensity(led_X, intensity=i, verbose=False, source_of_event="gli2")
        adc.take_reading()
        if getattr(adc, f"A{pd_X}") >= 2.048:
            X_max = i - 1
            led_intensity(led_X, 0, verbose=False, source_of_event="gli2")
            break
    else:
        X_max = 100

    # Y next
    for i in range(1, 100):
        led_intensity(led_Y, intensity=i, verbose=False, source_of_event="gli2")
        adc.take_reading()
        if getattr(adc, f"A{pd_Y}") >= 2.048:
            Y_max = i - 1
            led_intensity(led_Y, 0, verbose=False, source_of_event="gli2")
            break
    else:
        Y_max = 100

    def make_measurement():
        led_intensity(led_Y, intensity=0, verbose=False, source_of_event="gli2")
        led_intensity(led_X, intensity=X_max, verbose=False, source_of_event="gli2")

        adc.take_reading()
        signal1 = (getattr(adc, f"A{pd_Y}") - baselineY) / (
            getattr(adc, f"A{pd_X}") - baselineX
        )

        led_intensity(led_X, intensity=0, verbose=False, source_of_event="gli2")
        led_intensity(led_Y, intensity=Y_max, verbose=False, source_of_event="gli2")

        adc.take_reading()
        signal2 = (getattr(adc, f"A{pd_X}") - baselineX) / (
            getattr(adc, f"A{pd_Y}") - baselineY
        )

        led_intensity(led_X, intensity=0, verbose=False, source_of_event="gli2")
        led_intensity(led_Y, intensity=0, verbose=False, source_of_event="gli2")
        return sqrt(signal1 * signal2)

    signal = make_measurement()
    adc.set_state(adc.DISCONNECTED)

    return signal


@click.command(name="gli2")
def click_gli2():
    """
    Take a GLI Method 2 measurement, uncalibrated output.
    """
    try:
        led_X = config.get("gli2", "ir_led_X")
        led_Y = config.get("gli2", "ir_led_Y")

        pd_X = config.getint("gli2", "pd_X")
        pd_Y = config.getint("gli2", "pd_Y")
    except KeyError:
        raise KeyError(
            """
Requires following populated in config.ini:

[gli2]
ir_led_X=
ir_led_Y=
pd_X=
pd_Y=

        """
        )
    click.echo(
        gli2(
            pd_X,
            pd_Y,
            led_X,
            led_Y,
            unit=get_unit_name(),
            experiment=UNIVERSAL_EXPERIMENT,
        )
    )
    return


if __name__ == "__main__":
    click_gli2()
