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

# /sys/ pwm interface described here: http://www.jumpnowtek.com/rpi/Using-the-Raspberry-Pi-Hardware-PWM-timers.html
class HardwarePWM:

    chippath = "/sys/class/pwm/pwmchip0"

    def __init__(self, pwm):
        self.pwm = pwm
        self.pwmdir = f"{self.chippath}/pwm{self.pwm}"
        if not self.overlay_loaded():
            raise HardwarePWMException(
                "Need to add 'dtoverlay=pwm-2chan' to /boot/config.txt and reboot"
            )
        if not self.export_writable():
            raise HardwarePWMException(f"Need write access to files in '{self.chippath}'")
        if not self.pwmX_exists():
            self.create_pwmX()
        return

    def overlay_loaded(self):
        return os.path.isdir(self.chippath)

    def export_writable(self):
        return os.access(f"{self.chippath}/export", os.W_OK)

    def pwmX_exists(self):
        return os.path.isdir(self.pwmdir)

    def echo(self, m, fil):
        with open(fil, "w") as f:
            f.write(f"{m}\n")

    def create_pwmX(self):
        pwmexport = f"{self.chippath}/export"
        self.echo(self.pwm, pwmexport)

    def enable(self, disable=False):
        enable = f"{self.pwmdir}/enable"
        num = 1
        if disable:
            num = 0
        self.echo(num, enable)

    def disable(self):
        return self.enable(disable=True)

    def set_duty_cycle(self, milliseconds):
        # /sys/ iface, 2ms is 2000000
        # gpio cmd,    2ms is 200
        dc = int(milliseconds * 1_000_000)
        duty_cycle = f"{self.pwmdir}/duty_cycle"
        self.echo(dc, duty_cycle)

    def set_frequency(self, hz):
        per = 1 / float(hz)
        per *= 1000  # now in milliseconds
        per *= 1_000_000  # now in.. whatever
        per = int(per)
        period = f"{self.pwmdir}/period"
        self.echo(per, period)
