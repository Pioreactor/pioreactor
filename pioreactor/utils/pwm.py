# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from json import dumps
from os import getpid
from typing import Any
from typing import Iterator
from typing import Optional

import lgpio

from pioreactor.exc import PWMError
from pioreactor.logging import create_logger
from pioreactor.logging import Logger
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.types import GpioPin
from pioreactor.utils import clamp
from pioreactor.utils import gpio_helpers
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_latest_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

if is_testing_env():
    from pioreactor.utils.mock import MockPWMOutputDevice
    from pioreactor.utils.mock import MockHardwarePWM as HardwarePWM
else:
    try:
        from rpi_hardware_pwm import HardwarePWM  # type: ignore
    except ImportError:
        pass


class HardwarePWMOutputDevice(HardwarePWM):
    HARDWARE_PWM_CHANNELS: dict[GpioPin, int] = {12: 0, 13: 1}

    def __init__(self, pin: GpioPin, initial_dc: float = 0.0, frequency=100):
        if (
            pin not in self.HARDWARE_PWM_CHANNELS
        ):  # Only GPIO pins 18 and 19 are supported for hardware PWM
            raise ValueError(
                "Only GPIO pins 12 (PWM channel 0) and 13 (PWM channel 1) are supported."
            )

        pwm_channel = self.HARDWARE_PWM_CHANNELS[pin]
        super().__init__(pwm_channel, hz=frequency)
        self._dc = initial_dc

    def start(self):
        super().start(self.dc)

    def off(self):
        self.dc = 0.0

    @property
    def dc(self) -> float:
        return self._dc

    @dc.setter
    def dc(self, dc: float) -> None:
        dc = clamp(0.0, dc, 100.0)
        self.change_duty_cycle(dc)
        self._dc = dc

    def close(self):
        pass


class SoftwarePWMOutputDevice:
    def __init__(self, pin: GpioPin, initial_dc: float = 0.0, frequency=100):
        self.pin = pin
        self._dc = initial_dc
        self.frequency = frequency
        self._started = False
        self._handle = lgpio.gpiochip_open(0)

        lgpio.gpio_claim_output(self._handle, self.pin)
        lgpio.tx_pwm(self._handle, self.pin, self.frequency, self.dc)

    def start(self):
        self._started = True
        lgpio.tx_pwm(self._handle, self.pin, self.frequency, self.dc)

    def off(self):
        try:
            self.dc = 0.0
        except lgpio.error:
            # see issue #435
            pass

    @property
    def dc(self) -> float:
        return self._dc

    @dc.setter
    def dc(self, dc: float) -> None:
        dc = clamp(0.0, dc, 100.0)
        self._dc = dc
        if self._started:
            lgpio.tx_pwm(self._handle, self.pin, self.frequency, self.dc)

    def close(self):
        lgpio.gpiochip_close(self._handle)


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
    > pwm.clean_up() # make sure to cleanup! Or use context manager, see below.


    Use as a context manager:

    >with PMW(12, 15) as pwm:
    >    pwm.start(100)
    >    time.sleep(10)
    >    pwm.stop()


    > # locking
    > pwm.lock()
    > pwm.is_locked() # true, and will be true for any other PWM on this channel.
    > pwm.unlock()
    > pwm.is_locked() # false, .clean_up() and Python's deconstruction will also unlock.
    >
    > with pwm.lock_temporarily():
    >    # do stuff, will unlock on exit of context statement.
    >
    """

    HARDWARE_PWM_CHANNELS: set[GpioPin] = {12, 13}

    def __init__(
        self,
        pin: GpioPin,
        hz: float,
        unit: Optional[str] = None,
        experiment: Optional[str] = None,
        always_use_software: bool = False,
        pubsub_client: Optional[Client] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        self.unit = unit or get_unit_name()
        self.experiment = experiment or get_latest_experiment_name()

        if pubsub_client is None:
            self._external_client = False
            self.pubsub_client = create_client(client_id=f"pwm-{unit}-{experiment}-{pin}")
        else:
            self._external_client = True
            self.pubsub_client = pubsub_client

        if logger is None:
            self.logger = create_logger(
                f"PWM@GPIO-{pin}", experiment=self.experiment, unit=self.unit
            )
        else:
            self.logger = logger

        self.pin: GpioPin = pin
        self.hz = hz
        self.duty_cycle = 0.0

        if self.is_locked():
            msg = f"GPIO-{self.pin} is currently locked but a task is overwriting it. Either too many jobs are trying to access this pin, or a job didn't clean up properly."

            self.logger.error(msg)
            raise PWMError(msg)

        gpio_helpers.set_gpio_availability(self.pin, False)

        self._pwm: HardwarePWMOutputDevice | SoftwarePWMOutputDevice | MockPWMOutputDevice

        if is_testing_env():
            self._pwm = MockPWMOutputDevice(self.pin, 0, self.hz)
        elif (not always_use_software) and (pin in self.HARDWARE_PWM_CHANNELS):
            self._pwm = HardwarePWMOutputDevice(self.pin, 0, self.hz)
        else:
            if self.hz >= 1000:
                self.logger.warning(
                    "Setting a PWM to a very high frequency with software. Did you mean to use a hardware PWM?"
                )

            self._pwm = SoftwarePWMOutputDevice(self.pin, 0, self.hz)

        with local_intermittent_storage("pwm_hz") as cache:
            cache[self.pin] = self.hz

        self.logger.debug(
            f"Initialized GPIO-{self.pin} using {'hardware' if self.using_hardware else 'software'}-timing, initial frequency = {self.hz} hz."
        )

    @property
    def using_hardware(self) -> bool:
        try:
            return isinstance(self._pwm, HardwarePWMOutputDevice)
        except AttributeError:
            return False

    def _serialize(self):
        # don't send 0 values to MQTT - waste of space and time
        if self.duty_cycle > 0:
            current_values = {self.pin: self.duty_cycle}
        else:
            current_values = {}

        with local_intermittent_storage("pwm_dc") as cache:
            if self.duty_cycle > 0:
                cache[self.pin] = self.duty_cycle
            elif self.pin in cache and self.duty_cycle == 0:
                cache.pop(self.pin)
            # else: # self.duty_cycle == 0 and self.pin not in cache, leave it.

            for k in cache:
                if k == self.pin:
                    continue
                current_values[k] = cache[k]

        self.pubsub_client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/pwms/dc", dumps(current_values), retain=True
        )

    def start(self, initial_duty_cycle: float) -> None:
        if not (0.0 <= initial_duty_cycle <= 100.0):
            raise PWMError("duty_cycle should be between 0 and 100, inclusive.")

        self.change_duty_cycle(initial_duty_cycle)
        self._pwm.start()

    def stop(self) -> None:
        self._pwm.off()
        self.change_duty_cycle(0.0)

    def change_duty_cycle(self, duty_cycle: float) -> None:
        if not (0.0 <= duty_cycle <= 100.0):
            raise PWMError("duty_cycle should be between 0 and 100, inclusive.")

        self._pwm.dc = duty_cycle

        self.duty_cycle = round(float(duty_cycle), 5)

        self._serialize()

    def clean_up(self) -> None:
        self.stop()
        self._pwm.close()

        self.unlock()

        with local_intermittent_storage("pwm_dc") as cache:
            cache.pop(self.pin)

        with local_intermittent_storage("pwm_hz") as cache:
            cache.pop(self.pin)

        gpio_helpers.set_gpio_availability(self.pin, True)

        self.logger.debug(f"Cleaned up GPIO-{self.pin}.")

        if not self._external_client:
            self.pubsub_client.loop_stop()
            self.pubsub_client.disconnect()

    def is_locked(self) -> bool:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            return pwm_locks.get(self.pin) is not None

    def lock(self) -> None:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            pwm_locks[self.pin] = getpid()

    def unlock(self) -> None:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            if self.pin in pwm_locks:
                del pwm_locks[self.pin]

    @contextmanager
    def lock_temporarily(self) -> Iterator[None]:
        try:
            self.lock()
            yield
        finally:
            self.unlock()

    def __exit__(self, *args: Any) -> None:
        self.clean_up()

    def __enter__(self) -> PWM:
        return self
