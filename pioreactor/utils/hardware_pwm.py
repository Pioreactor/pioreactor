#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os.path

# Copyright 2018 Jeremy Impson <jdimpson@acm.org>

# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 3 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.
# See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <http://www.gnu.org/licenses>.


class HardwarePWMException(Exception):
    pass


# pwm0 is GPIO pin 18 is physical pin 12
# pwm1 is GPIO pin 19 is physical pin 13

# /sys/ pwm interface described here: https://www.jumpnowtek.com/rpi/Using-the-Raspberry-Pi-Hardware-PWM-timers.html
class HardwarePWM:
    """

    Example
    ----------
    >pwm = HardwarePWM(0)
    >pwm.set_frequency(20)
    >pwm.start(100)
    >pwm.ChangeDutyCycle(50)
    >pwm.stop()

    Notes
    --------
    If you get "write error: Invalid argument" - you have to set duty_cycle to 0 before changing period

    """

    chippath = "/sys/class/pwm/pwmchip0"

    def __init__(self, pwm_channel, hz):
        self.pwm_channel = pwm_channel
        self.pwm_dir = f"{self.chippath}/pwm{self.pwm_channel}"
        if not self.is_overlay_loaded():
            raise HardwarePWMException(
                "Need to add 'dtoverlay=pwm-2chan' to /boot/config.txt and reboot"
            )
        if not self.is_export_writable():
            raise HardwarePWMException(f"Need write access to files in '{self.chippath}'")
        if not self.does_pwmX_exists():
            self.create_pwmX()

        self.set_frequency(hz)

    def is_overlay_loaded(self):
        return os.path.isdir(self.chippath)

    def is_export_writable(self):
        return os.access(os.path.join(self.chippath, "export"), os.W_OK)

    def does_pwmX_exists(self):
        return os.path.isdir(self.pwm_dir)

    def echo(self, m, fil):
        with open(fil, "w") as f:
            f.write(f"{m}\n")

    def create_pwmX(self):
        self.echo(self.pwm_channel, os.path.join(self.chippath, "export"))

    def start(self, initial_duty_cycle):
        self.change_duty_cycle(initial_duty_cycle)
        self.echo(1, os.path.join(self.pwm_dir, "enable"))

    def stop(self):
        self.change_duty_cycle(0)
        self.set_frequency(0)
        self.echo(0, os.path.join(self.pwm_dir, "enable"))

    def change_duty_cycle(self, duty_cycle):
        # a value between 0 and 100
        assert 0 <= duty_cycle <= 100
        per = 1 / float(self._hz)
        per *= 1000  # now in milliseconds
        per *= 1_000_000  # now in.. whatever
        dc = int(per * duty_cycle / 100)
        self.echo(dc, os.path.join(self.pwm_dir, "duty_cycle"))

    def set_frequency(self, hz):
        self._hz = hz
        per = 1 / float(self._hz)
        per *= 1000  # now in milliseconds
        per *= 1_000_000  # now in.. whatever
        per = int(per)
        self.echo(per, os.path.join(self.pwm_dir, "period"))
