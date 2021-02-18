# -*- coding: utf-8 -*-

from math import sqrt
import click

from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.actions.led_intensity import led_intensity
from pioreactor.config import config
from pioreactor.utils import pio_jobs_running


def gli2(pd_A, pd_B, led_A, led_B, unit=None, experiment=None):
    """
    Advisable that stirring is turned on. OD reading should be turned off.

    The pd_X and led_X are the (integer) channels on the Pioreactor HAT. They map to the pairs of pockets at 90° angles in the Pioreactor, see below



               pd_B
           , - ~ ~ ~ - ,
      x, '               ' ,x
     ,                       ,
    ,                         ,
   ,                           ,
 led_A                        pd_A
   ,                           ,
    ,                         ,
     ,                       ,
      x,                  , 'x
         ' - , _ _ _ ,  '
               led_B

    """
    assert "od_reading" not in pio_jobs_running(), "Turn off od_reading job first."

    adc = ADCReader(unit=unit, experiment=experiment, dynamic_gain=False)
    adc.setup_adc()

    # reset all to 0
    led_intensity(led_A, intensity=0, verbose=True, source_of_event="gli2")
    led_intensity(led_B, intensity=0, verbose=True, source_of_event="gli2")

    # find values of LED intensity s.t. we don't overload the 180 degree sensor, i.e. aim for 2.25V, or max
    # A first
    for i in range(1, 100):
        led_intensity(led_A, intensity=i, verbose=True, source_of_event="gli2")
        adc.take_reading()
        if getattr(adc, f"A{pd_A}") >= 2.048:
            A_max = i - 1
            led_intensity(led_A, 0, verbose=True, source_of_event="gli2")
            break
    else:
        A_max = 100

    # B next
    for i in range(1, 100):
        led_intensity(led_B, intensity=i, verbose=True, source_of_event="gli2")
        adc.take_reading()
        if getattr(adc, f"A{pd_B}") >= 2.048:
            B_max = i - 1
            led_intensity(led_B, 0, verbose=True, source_of_event="gli2")
            break
    else:
        B_max = 100

    def make_measurement():
        led_intensity(led_B, intensity=0, verbose=True, source_of_event="gli2")
        led_intensity(led_A, intensity=A_max, verbose=True, source_of_event="gli2")

        adc.take_reading()
        signal1 = getattr(adc, f"A{pd_B}") / getattr(adc, f"A{pd_A}")

        led_intensity(led_A, intensity=0, verbose=True, source_of_event="gli2")
        led_intensity(led_B, intensity=B_max, verbose=True, source_of_event="gli2")

        adc.take_reading()
        signal2 = getattr(adc, f"A{pd_A}") / getattr(adc, f"A{pd_B}")

        led_intensity(led_A, intensity=0, verbose=True, source_of_event="gli2")
        led_intensity(led_B, intensity=0, verbose=True, source_of_event="gli2")
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
        led_A = config.get("leds", "ir_ledA")
        led_B = config.get("leds", "ir_ledB")

        pd_A = config.getint("pd_inputs", "pd_A")
        pd_B = config.getint("pd_inputs", "pd_B")
    except KeyError:
        raise KeyError(
            """
Requires following populated in config.ini:

[leds]
ir_ledA=
ir_ledB=

[pd_inputs]
pd_A=
pd_B=

        """
        )
    return gli2(pd_A, pd_B, led_A, led_B)


if __name__ == "__main__":
    print(click_gli2())
