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

    def update_intensity(channel, intensity):
        led_intensity(
            channel,
            intensity=intensity,
            verbose=False,
            source_of_event="gli2",
            unit=unit,
            experiment=experiment,
        )

    def adc_reading(adc, channel):
        return getattr(adc, f"A{channel}")

    assert "od_reading" not in pio_jobs_running(), "Turn off od_reading job first."

    adc = ADCReader(unit=unit, experiment=experiment, initial_gain=2, dynamic_gain=False)
    adc.setup_adc()

    # reset all to 0
    update_intensity(led_X, 0)
    update_intensity(led_Y, 0)

    # take baseline measurements
    adc.take_reading()
    baselineX = adc_reading(adc, "X")
    baselineY = adc_reading(adc, "Y")

    # find values of LED intensity s.t. we don't overload the 180 degree sensor
    # X first
    for i in range(1, 100):
        update_intensity(led_X, i)
        adc.take_reading()
        if adc_reading(adc, "X") >= 2.048:
            X_max = i - 1
            update_intensity(led_X, 0)
            break
    else:
        X_max = 100

    # Y next
    for i in range(1, 100):
        update_intensity(led_Y, i)
        adc.take_reading()
        if adc_reading(adc, "Y") >= 2.048:
            Y_max = i - 1
            update_intensity(led_Y, 0)
            break
    else:
        Y_max = 100

    def make_measurement():
        update_intensity(led_Y, 0)
        update_intensity(led_X, X_max)

        adc.take_reading()
        signal1 = (adc_reading(adc, "Y") - baselineY) / (
            adc_reading(adc, "X") - baselineX
        )

        update_intensity(led_X, 0)
        update_intensity(led_Y, Y_max)

        adc.take_reading()
        signal2 = (adc_reading(adc, "X") - baselineX) / (
            adc_reading(adc, "Y") - baselineY
        )

        update_intensity(led_X, 0)
        update_intensity(led_Y, 0)
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
