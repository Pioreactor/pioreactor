# -*- coding: utf-8 -*-
import sys, threading, signal, os
from pioreactor.whoami import is_testing_env
from pioreactor.logging import create_logger

if is_testing_env():
    import fake_rpi

    sys.modules["RPi"] = fake_rpi.RPi  # Fake RPi
    sys.modules["RPi.GPIO"] = fake_rpi.RPi.GPIO  # Fake GPIO

import RPi.GPIO as GPIO

GPIO.setmode(GPIO.BCM)


class PWM:
    """
    This class abstracts out the Rpi's PWM library details


    Notes
    -------
    There is a soft locking feature, `lock` and `is_locked`, that a program can use to
    present other programs from using the PWM channel. This may move to a hard lock in the future.



    Example
    -----------
    > from pioreactor.utils.pwm import PWM
    > pwm = PWM(12, 50)
    > pwm.start(20) # 20% duty cycle
    >
    > pwm.change_duty_cycle(25) # 25% duty cycle
    >
    > pwm.stop()
    > pwm.cleanup()
    >
    > # locking
    > pwm.lock()
    > pwm.is_locked() # true, and will be true for any other PWM on this channel.
    > pwm.unlock()
    > pwm.is_locked() # false, .cleanup() will also unlock.
    """

    HARDWARE_PWM_AVAILABLE_PINS = {12, 13}
    HARDWARE_PWM_CHANNELS = {12: 0, 13: 1}
    LOCK_FOLDER = "/tmp/" if not is_testing_env() else "./"
    using_hardware = False

    def __init__(self, pin, hz, always_use_software=False):
        self.logger = create_logger("PWM")
        self.pin = pin
        self.hz = hz
        self.lock_file_location = os.path.join(self.LOCK_FOLDER, f".PWM-{self.pin}-lock")

        if (not always_use_software) and (pin in self.HARDWARE_PWM_AVAILABLE_PINS):
            if is_testing_env():
                from pioreactor.utils.mock import MockHardwarePWM as HardwarePWM
            else:
                from rpi_hardware_pwm import HardwarePWM

            self.pwm = HardwarePWM(self.HARDWARE_PWM_CHANNELS[self.pin], self.hz)
            self.using_hardware = True

        else:
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, 0)
            self.pwm = GPIO.PWM(self.pin, hz)

        self.logger.debug(
            f"Initialized PWM-{self.pin} with {'hardware' if self.using_hardware else 'software'}."
        )

        # signals only work in main thread
        if threading.current_thread() is threading.main_thread():
            # terminate command, ex: pkill
            def on_kill(*args):
                self.cleanup()
                sys.exit()

            signal.signal(signal.SIGTERM, on_kill)
            signal.signal(signal.SIGINT, on_kill)

    def start(self, initial_duty_cycle):
        self.pwm.start(initial_duty_cycle)

    def stop(self):
        self.pwm.stop()

    def change_duty_cycle(self, dc):
        if self.using_hardware:
            self.pwm.change_duty_cycle(dc)
        else:
            self.pwm.ChangeDutyCycle(dc)

    def cleanup(self):
        self.stop()
        self.unlock()
        if self.using_hardware:
            # `stop` handles cleanup.
            pass
        else:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, 0)
            GPIO.cleanup(self.pin)
        self.logger.debug(f"Cleaned up PWM-{self.pin}.")

    def is_locked(self):
        return os.path.isfile(self.lock_file_location)

    def lock(self):
        try:
            open(self.lock_file_location, "x")
        except FileExistsError:
            pass

    def unlock(self):
        try:
            os.remove(self.lock_file_location)
        except OSError:
            pass

    def __exit__(self):
        self.cleanup()
