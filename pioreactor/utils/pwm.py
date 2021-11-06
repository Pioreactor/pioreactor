# -*- coding: utf-8 -*-
from contextlib import contextmanager
from pioreactor.whoami import is_testing_env
from pioreactor.logging import create_logger
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils import gpio_helpers

if is_testing_env():
    from pioreactor.utils.mock import MockHardwarePWM as HardwarePWM
else:
    from rpi_hardware_pwm import HardwarePWM  # type: ignore

PWM_LOCKED = b"1"
PWM_UNLOCKED = b"0"


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
    > pwm.cleanup() # make sure to cleanup! Or use context manager, see below.


    Use as a context manager:

    >with PMW(12, 15) as pwm:
    >    pwm.start(100
    >    time.sleep(10)


    > # locking
    > pwm.lock()
    > pwm.is_locked() # true, and will be true for any other PWM on this channel.
    > pwm.unlock()
    > pwm.is_locked() # false, .cleanup() and Python's deconstruction will also unlock.
    >
    > with pwm.lock_temporarily():
    >    # do stuff, will unlock on exit of context statement.
    >
    """

    HARDWARE_PWM_AVAILABLE_PINS = {12, 13}
    HARDWARE_PWM_CHANNELS = {12: 0, 13: 1}

    def __init__(self, pin: int, hz: float, always_use_software: bool = False):
        self.logger = create_logger("PWM")
        self.pin = pin
        self.hz = hz

        if self.is_locked():
            self.logger.warning(
                f"PWM-{self.pin} is currently locked but a task is trying to use it."
            )

        gpio_helpers.set_gpio_availability(
            self.pin, gpio_helpers.GPIO_states.GPIO_UNAVAILABLE
        )

        if (not always_use_software) and (pin in self.HARDWARE_PWM_AVAILABLE_PINS):

            self.pwm = HardwarePWM(self.HARDWARE_PWM_CHANNELS[self.pin], self.hz)

        else:

            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)

            if self.hz > 5000:
                self.logger.warning(
                    "Setting a PWM to a very high frequency with software. Did you mean to use a hardware PWM?"
                )

            self.pwm = GPIO.PWM(self.pin, self.hz)

        with local_intermittent_storage("pwm_hz") as cache:
            cache[str(self.pin)] = str(self.hz)

        self.logger.debug(
            f"Initialized PWM-{self.pin} with {'hardware' if self.using_hardware else 'software'}, initial frequency is {self.hz}hz."
        )

    @property
    def using_hardware(self):
        try:
            return isinstance(self.pwm, HardwarePWM)
        except AttributeError:
            return False

    def start(self, initial_duty_cycle: float):
        assert (
            0.0 <= initial_duty_cycle <= 100.0
        ), "dc should be between 0 and 100, inclusive."

        with local_intermittent_storage("pwm_dc") as cache:
            cache[str(self.pin)] = str(initial_duty_cycle)

        self.pwm.start(initial_duty_cycle)

    def stop(self):
        self.pwm.stop()

    def change_duty_cycle(self, dc: float):
        assert 0 <= dc <= 100, "dc should be between 0 and 100, inclusive."

        with local_intermittent_storage("pwm_dc") as cache:
            cache[str(self.pin)] = str(dc)

        if self.using_hardware:
            self.pwm.change_duty_cycle(dc)
        else:
            self.pwm.ChangeDutyCycle(dc)  # type: ignore

    def cleanup(self):
        self.stop()
        self.unlock()

        with local_intermittent_storage("pwm_dc") as cache:
            if str(self.pin) in cache:
                del cache[str(self.pin)]

        with local_intermittent_storage("pwm_hz") as cache:
            if str(self.pin) in cache:
                del cache[str(self.pin)]

        gpio_helpers.set_gpio_availability(
            self.pin, gpio_helpers.GPIO_states.GPIO_AVAILABLE
        )

        if self.using_hardware:
            # `stop` handles cleanup.
            pass
        else:

            import RPi.GPIO as GPIO

            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.cleanup(self.pin)

        self.logger.debug(f"Cleaned up PWM-{self.pin}.")

    def is_locked(self) -> bool:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            return pwm_locks.get(str(self.pin)) == PWM_LOCKED

    def lock(self):
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            pwm_locks[str(self.pin)] = PWM_LOCKED

    def unlock(self):
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            pwm_locks[str(self.pin)] = PWM_UNLOCKED

    @contextmanager
    def lock_temporarily(self):
        try:
            self.lock()
            yield
        finally:
            self.unlock()

    def __exit__(self, *args):
        self.cleanup()

    def __enter__(self):
        return self
