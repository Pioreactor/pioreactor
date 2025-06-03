# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import contextmanager
from contextlib import suppress
from json import dumps
from os import getpid
from typing import Any
from typing import Iterator
from typing import Optional

from pioreactor import types as pt
from pioreactor.exc import PWMError
from pioreactor.hardware import GPIOCHIP
from pioreactor.logging import create_logger
from pioreactor.logging import CustomLogger
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.types import GpioPin
from pioreactor.utils import clamp
from pioreactor.utils import local_intermittent_storage
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

if is_testing_env():
    from pioreactor.utils.mock import MockPWMOutputDevice
    from pioreactor.utils.mock import MockHardwarePWM as HardwarePWM
else:
    from rpi_hardware_pwm import HardwarePWM  # type: ignore


class HardwarePWMOutputDevice(HardwarePWM):
    HARDWARE_PWM_CHANNELS: dict[GpioPin, int] = {12: 0, 13: 1}
    _started = False

    def __init__(self, pin: GpioPin, frequency: float = 100) -> None:
        if pin not in self.HARDWARE_PWM_CHANNELS:  # Only GPIO pins 18 and 19 are supported for hardware PWM
            raise ValueError("Only GPIO pins 12 (PWM channel 0) and 13 (PWM channel 1) are supported.")

        pwm_channel = self.HARDWARE_PWM_CHANNELS[pin]

        import platform
        from pioreactor.version import rpi_version_info

        if rpi_version_info.startswith("Raspberry Pi 5") and "Linux-6.6" in platform.platform():
            # default is chip=0 for all except RPi5 on Kernel 6.6 (which is 2)
            super().__init__(pwm_channel, hz=frequency, chip=2)
        else:
            super().__init__(pwm_channel, hz=frequency, chip=0)

    def start(self, initial_dc: pt.FloatBetween0and100) -> None:
        self._started = True
        super().start(initial_dc)
        self._dc = initial_dc

    def off(self) -> None:
        self.dc = 0.0

    @property
    def dc(self) -> pt.FloatBetween0and100:
        return self._dc

    @dc.setter
    def dc(self, dc: pt.FloatBetween0and100) -> None:
        if self._started:
            dc = clamp(0.0, dc, 100.0)
            self.change_duty_cycle(dc)
            self._dc = dc
        elif dc == 0:
            pass
        else:
            raise ValueError("must call .start() first!")

    def close(self) -> None:
        self._started = False
        pass


class SoftwarePWMOutputDevice:
    _started = False

    def __init__(self, pin: GpioPin, frequency: float = 100) -> None:
        import lgpio

        self.pin = pin
        self.frequency = frequency
        self._handle = lgpio.gpiochip_open(GPIOCHIP)

        lgpio.gpio_claim_output(self._handle, self.pin)
        lgpio.tx_pwm(self._handle, self.pin, self.frequency, 0)

    def start(self, initial_dc: pt.FloatBetween0and100) -> None:
        import lgpio

        self._started = True
        self.dc = initial_dc
        lgpio.tx_pwm(self._handle, self.pin, self.frequency, self.dc)

    def off(self) -> None:
        self.dc = 0.0

    @property
    def dc(self) -> pt.FloatBetween0and100:
        return self._dc

    @dc.setter
    def dc(self, dc: pt.FloatBetween0and100) -> None:
        import lgpio

        dc = clamp(0.0, dc, 100.0)
        self._dc = dc
        if self._started:
            try:
                lgpio.tx_pwm(self._handle, self.pin, self.frequency, self.dc)
            except lgpio.error:
                pass
        elif dc == 0:
            pass
        else:
            raise ValueError("must call .start() first!")

    def close(self):
        import lgpio

        self._started = False
        try:
            lgpio.gpiochip_close(self._handle)
        except lgpio.error:
            # not sure why this happens.
            pass


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
        pub_client: Optional[Client] = None,
        logger: Optional[CustomLogger] = None,
    ) -> None:
        self.unit = unit or get_unit_name()
        self.experiment = experiment or get_assigned_experiment_name(self.unit)

        if pub_client is None:
            self._external_client = False
            self.pub_client = create_client(client_id=f"pwm-{self.unit}-{experiment}-{pin}")
        else:
            self._external_client = True
            self.pub_client = pub_client

        if logger is None:
            self.logger = create_logger(f"PWM@GPIO-{pin}", experiment=self.experiment, unit=self.unit)
        else:
            self.logger = logger

        self.pin: GpioPin = pin
        self.hz = hz
        self.duty_cycle = 0.0

        if self.is_locked():
            msg = f"GPIO-{self.pin} is currently locked but a task is overwriting it. Either too many jobs are trying to access this pin, or a job didn't clean up properly. If your confident you can release it, use `pio cache clear pwm_locks {self.pin} --as-int` on the command line for {self.unit}."

            self.logger.error(msg)
            raise PWMError(msg)

        self._pwm: HardwarePWMOutputDevice | SoftwarePWMOutputDevice | MockPWMOutputDevice

        if is_testing_env():
            self._pwm = MockPWMOutputDevice(self.pin, self.hz)
        elif (not always_use_software) and (pin in self.HARDWARE_PWM_CHANNELS):
            self._pwm = HardwarePWMOutputDevice(self.pin, self.hz)
        else:
            if self.hz >= 1000:
                self.logger.warning(
                    "Setting a PWM to a very high frequency with software. Did you mean to use a hardware PWM?"
                )

            self._pwm = SoftwarePWMOutputDevice(self.pin, self.hz)

        self.logger.debug(
            f"Initialized GPIO-{self.pin} using {'hardware' if self.using_hardware else 'software'}-timing, initial frequency = {self.hz} hz."
        )

    @property
    def using_hardware(self) -> bool:
        try:
            return isinstance(self._pwm, HardwarePWMOutputDevice)
        except AttributeError:
            return False

    def _serialize(self) -> None:
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
                # we use get here because if two processes are updating the cache, and one of them deletes from the cache,
                # this will raise a keyerror when we try to retrieve it.
                value = cache.get(k, 0)
                if value != 0:
                    current_values[k] = value

        self.pub_client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/pwms/dc", dumps(current_values), retain=True
        )

    def start(self, duty_cycle: pt.FloatBetween0and100) -> None:
        if not (0.0 <= duty_cycle <= 100.0):
            raise PWMError("duty_cycle should be between 0 and 100, inclusive.")

        self._pwm.start(duty_cycle)
        self.duty_cycle = round(float(duty_cycle), 5)
        self._serialize()

    def stop(self) -> None:
        self._pwm.off()
        self.change_duty_cycle(0.0)

    def change_duty_cycle(self, duty_cycle: pt.FloatBetween0and100) -> None:
        if not (0.0 <= duty_cycle <= 100.0):
            raise PWMError("duty_cycle should be between 0 and 100, inclusive.")

        self._pwm.dc = duty_cycle

        self.duty_cycle = round(float(duty_cycle), 5)

        self._serialize()

    def clean_up(self) -> None:
        with suppress(ValueError):
            # this is thrown if the _pwm hasn't started yet.
            self.stop()

        self._pwm.close()

        self.unlock()

        with local_intermittent_storage("pwm_dc") as cache:
            cache.pop(self.pin)

        self.logger.debug(f"Cleaned up GPIO-{self.pin}.")

        if not self._external_client:
            self.pub_client.loop_stop()
            self.pub_client.disconnect()

    def is_locked(self) -> bool:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            return pwm_locks.get(self.pin) is not None

    def lock(self) -> None:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            pwm_locks[self.pin] = getpid()

    def unlock(self) -> None:
        with local_intermittent_storage("pwm_locks") as pwm_locks:
            pwm_locks.pop(self.pin)

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
