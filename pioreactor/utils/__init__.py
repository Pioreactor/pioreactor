# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import signal
from contextlib import contextmanager
from threading import Event
from typing import Callable
from typing import Generator
from typing import overload

from diskcache import Cache  # type: ignore

from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.pubsub import create_client
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe_and_callback


class callable_stack:
    def __init__(self) -> None:
        self.callables: list[Callable] = []

    def append(self, function: Callable) -> None:
        self.callables.append(function)

    def __call__(self, *args) -> None:
        for function in reversed(self.callables):
            function(*args)


def append_signal_handler(signal_value: signal.Signals, new_callback: Callable) -> None:
    """
    The current api of signal.signal is a global stack of size 1, so if
    we have multiple jobs started in the same python process, we
    need them all to respect each others signal.
    """
    current_callback = signal.getsignal(signal_value)

    if callable(current_callback):
        if isinstance(current_callback, callable_stack):
            # we've previously added something to the handler..
            current_callback.append(new_callback)
            signal.signal(signal_value, current_callback)
        else:
            # no stack yet, default callable was present. Don't forget to add new callback, too
            stack = callable_stack()
            stack.append(current_callback)
            stack.append(new_callback)
            signal.signal(signal_value, stack)
    elif (current_callback is signal.SIG_DFL) or (current_callback is signal.SIG_IGN):
        # no stack yet.
        stack = callable_stack()
        stack.append(new_callback)
        signal.signal(signal_value, stack)
    elif current_callback is None:
        signal.signal(signal_value, callable_stack())
    else:
        raise RuntimeError(f"Something is wrong. Observed {current_callback}.")


def append_signal_handlers(signal_value: signal.Signals, new_callbacks: list[Callable]) -> None:
    for callback in new_callbacks:
        append_signal_handler(signal_value, callback)


class publish_ready_to_disconnected_state:
    """
    Wrap a block of code to have "state" in MQTT. See od_normalization, self_test, pump

    You can use MQTT ".../$state/set" tools to disconnect it.

    Example
    ----------

    > with publish_ready_to_disconnected_state(unit, experiment, "self_test"): # publishes "ready" to mqtt
    >    do_work()
    >
    > # on close of block, a "disconnected" is fired to MQTT, regardless of how that end is achieved (error, return statement, etc.)


    If the program is required to know if it's kill, publish_ready_to_disconnected_state contains an event (see pump.py code)

    > with publish_ready_to_disconnected_state(unit, experiment, "self_test") as state:
    >    do_work()
    >    state.exit_event.wait(60)
    >    if state.exit_event.is_set():
    >       bail!
    >

    TODO: just create a client in the __init__, and use that throughout.


    """

    def __init__(self, unit: str, experiment: str, name: str) -> None:
        self.unit = unit
        self.experiment = experiment
        self.name = name
        self.exit_event = Event()

        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            "payload": "lost",
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        self.client = create_client(
            client_id=f"{self.name}-{self.unit}-{self.experiment}",
            keepalive=3 * 60,
            last_will=last_will,
        )
        self.start_passive_listeners()

    def _exit(self, *args) -> None:
        self.exit_event.set()

    def __enter__(self) -> publish_ready_to_disconnected_state:
        try:
            # this only works on the main thread.
            append_signal_handler(signal.SIGTERM, self._exit)
            append_signal_handler(signal.SIGINT, self._exit)
        except ValueError:
            pass

        self.client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            "ready",
            qos=QOS.AT_LEAST_ONCE,
            retain=True,
        )

        with local_intermittent_storage("pio_jobs_running") as cache:
            cache[self.name] = os.getpid()

        return self

    def __exit__(self, *args) -> None:
        self.client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            "disconnected",
            qos=QOS.AT_LEAST_ONCE,
            retain=True,
        )
        self.client.loop_stop()
        self.client.disconnect()

        with local_intermittent_storage("pio_jobs_running") as cache:
            cache.pop(self.name)

        return

    def exit_from_mqtt(self, message: pt.MQTTMessage) -> None:
        if message.payload.decode() == "disconnected":
            self._exit()

    def start_passive_listeners(self) -> None:
        subscribe_and_callback(
            self.exit_from_mqtt,
            [
                f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state/set",
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.name}/$state/set",
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/{self.name}/$state/set",
                f"pioreactor/{self.unit}/{whoami.UNIVERSAL_EXPERIMENT}/{self.name}/$state/set",
            ],
            client=self.client,
        )
        return


@contextmanager
def local_intermittent_storage(
    cache_name: str,
) -> Generator[Cache, None, None]:
    """

    The cache is deleted upon a Raspberry Pi restart!

    Examples
    ---------
    > with local_intermittent_storage('pwm') as cache:
    >     assert '1' in cache
    >     cache['1'] = 0.5


    Notes
    -------
    Opening the same cache in a context manager is tricky, and should be avoided.

    """
    # TMPDIR is in OSX and Pioreactor img (we provide it), TMP is windows
    tmp_dir = os.environ.get("TMPDIR") or os.environ.get("TMP") or "/tmp/"
    cache = Cache(f"{tmp_dir}{cache_name}")
    try:
        yield cache  # type: ignore
    finally:
        cache.close()


@contextmanager
def local_persistant_storage(
    cache_name: str,
) -> Generator[Cache, None, None]:
    """
    Values stored in this storage will stay around between RPi restarts, and until overwritten
    or deleted.

    Examples
    ---------
    > with local_persistant_storage('od_blank') as cache:
    >     assert '1' in cache
    >     cache['1'] = 0.5

    """
    from pioreactor.whoami import is_testing_env

    if is_testing_env():
        cache = Cache(f".pioreactor/storage/{cache_name}")
    else:
        cache = Cache(f"/home/pioreactor/.pioreactor/storage/{cache_name}")

    try:
        yield cache  # type: ignore
    finally:
        cache.close()


def clamp(minimum: float | int, x: float | int, maximum: float | int) -> float:
    return max(minimum, min(x, maximum))


@overload
def is_pio_job_running(target_jobs: list[str]) -> list[bool]:
    ...


@overload
def is_pio_job_running(target_jobs: str) -> bool:
    ...


def is_pio_job_running(target_jobs):
    """
    pass in jobs to check if they are running
    ex:

    > result = is_pio_job_running("od_reading")

    > result = is_pio_job_running(["od_reading", "stirring"])
    """
    if isinstance(target_jobs, str):
        target_jobs = [target_jobs]

    results = []
    with local_intermittent_storage("pio_jobs_running") as cache:
        for job in target_jobs:
            if job not in cache:
                results.append(False)
            else:
                results.append(True)

    if len(target_jobs) == 1:
        return results[0]
    else:
        return results


def pump_ml_to_duration(ml: float, duration_: float = 0, bias_: float = 0) -> float:
    """
    ml: the desired volume
    duration_ : the coefficient from calibration
    """
    return (ml - bias_) / duration_


def pump_duration_to_ml(duration: float, duration_: float = 0, bias_: float = 0) -> float:
    """
    duration: the desired volume
    duration_ : the coefficient from calibration
    """
    return duration * duration_ + bias_


def get_cpu_temperature() -> float:
    if whoami.is_testing_env():
        return 22.0

    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
        cpu_temperature_celcius = int(f.read().strip()) / 1000.0
    return cpu_temperature_celcius


def argextrema(x: list) -> tuple[int, int]:
    min_, max_ = float("inf"), float("-inf")
    argmin_, argmax_ = 0, 0
    for i, value in enumerate(x):
        if value < min_:
            min_ = value
            argmin_ = i
        if value > max_:
            max_ = value
            argmax_ = i
    return argmin_, argmax_


class SummableList(list):
    def __add__(self, other) -> SummableList:
        return SummableList([s + o for (s, o) in zip(self, other)])

    def __iadd__(self, other) -> SummableList:
        return self + other
