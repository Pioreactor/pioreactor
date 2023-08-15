# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import signal
import tempfile
import time
from contextlib import contextmanager
from functools import wraps
from threading import Event
from typing import Callable
from typing import cast
from typing import Generator
from typing import Optional
from typing import overload

from diskcache import Cache  # type: ignore

from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.pubsub import create_client
from pioreactor.pubsub import QOS
from pioreactor.pubsub import subscribe_and_callback


class callable_stack:
    """
    A class for managing a stack of callable objects in Python.

    Example:
    >>> def greet(name):
    ... print(f"Hello, {name}!")
    ...
    >>> def goodbye(name):
    ... print(f"Goodbye, {name}!")
    ...
    >>> my_stack = callable_stack()
    >>> my_stack.append(greet)
    >>> my_stack.append(goodbye)
    >>> my_stack('Alice')
    Goodbye, Alice!
    Hello, Alice!
    """

    def __init__(self, default_function_if_empty: Callable = lambda *args: None) -> None:
        self._callables: list[Callable] = []
        self.default = default_function_if_empty

    def append(self, function: Callable) -> None:
        self._callables.append(function)

    def __call__(self, *args) -> None:
        if not self._callables:
            self.default(*args)

        while self._callables:
            function = self._callables.pop()
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
            stack = callable_stack(signal.default_int_handler)
            stack.append(current_callback)
            stack.append(new_callback)
            signal.signal(signal_value, stack)
    elif (current_callback is signal.SIG_DFL) or (current_callback is signal.SIG_IGN):
        # no stack yet.
        stack = callable_stack(signal.default_int_handler)
        stack.append(new_callback)
        signal.signal(signal_value, stack)
    elif current_callback is None:
        signal.signal(signal_value, callable_stack(signal.default_int_handler))
    else:
        raise RuntimeError(f"Something is wrong. Observed {current_callback}.")


def append_signal_handlers(signal_value: signal.Signals, new_callbacks: list[Callable]) -> None:
    for callback in new_callbacks:
        append_signal_handler(signal_value, callback)


class publish_ready_to_disconnected_state:
    """
    Wrap a block of code to have "state" in MQTT. See od_normalization, self_test, pump

    You can use send a "disconnected" to "pioreactor/<unit>/<exp>/<name>/$state/set" to stop/disconnect it.

    Example
    ----------

    > with publish_ready_to_disconnected_state(unit, experiment, "self_test"): # publishes "ready" to mqtt
    >    do_work()
    >
    > # on close of block, a "disconnected" is fired to MQTT, regardless of how that end is achieved (error, return statement, etc.)


    If the program is required to know if it's killed, publish_ready_to_disconnected_state contains an event (see pump.py code)

    > with publish_ready_to_disconnected_state(unit, experiment, "self_test") as state:
    >    do_work()
    >
    >    state.block_until_disconnected()
    >    # or state.exit_event.is_set() or state.exit_event.wait(...) are other options.
    >

    """

    def __init__(
        self,
        unit: str,
        experiment: str,
        name: str,
        exit_on_mqtt_disconnect: bool = False,
        mqtt_client_kwargs: Optional[dict] = None,
    ) -> None:
        self.unit = unit
        self.experiment = experiment
        self.name = name
        self.state = "init"
        self.exit_event = Event()

        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            "payload": b"lost",
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        default_mqtt_client_kwargs = {
            "keepalive": 5 * 60,
            "client_id": f"{self.name}-{self.unit}-{self.experiment}",
        }

        self.client = create_client(
            last_will=last_will,
            on_disconnect=self._on_disconnect if exit_on_mqtt_disconnect else None,
            **(default_mqtt_client_kwargs | (mqtt_client_kwargs or dict())),  # type: ignore
        )

        self.start_passive_listeners()

    def _exit(self, *args) -> None:
        # recall: we can't publish in a callback!
        self.exit_event.set()

    def _on_disconnect(self, *args):
        self._exit()

    def __enter__(self) -> publish_ready_to_disconnected_state:
        try:
            # this only works on the main thread.
            append_signal_handler(signal.SIGTERM, self._exit)
            append_signal_handler(signal.SIGINT, self._exit)
        except ValueError:
            pass

        self.state = "ready"
        self.client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            self.state,
            qos=QOS.AT_LEAST_ONCE,
            retain=True,
        )

        with local_intermittent_storage("pio_jobs_running") as cache:
            cache[self.name] = os.getpid()

        return self

    def __exit__(self, *args) -> None:
        self.state = "disconnected"
        self.client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.name}/$state",
            b"disconnected",
            qos=QOS.AT_LEAST_ONCE,
            retain=True,
        )
        self.client.loop_stop()
        self.client.disconnect()

        with local_intermittent_storage("pio_jobs_running") as cache:
            cache.pop(self.name)
        return

    def exit_from_mqtt(self, message: pt.MQTTMessage) -> None:
        if message.payload == b"disconnected":
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

    def block_until_disconnected(self) -> None:
        self.exit_event.wait()


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
    # gettempdir find the directory named by the TMPDIR environment variable.
    # TMPDIR is set in the Pioreactor img.
    tmp_dir = tempfile.gettempdir()
    with Cache(f"{tmp_dir}/{cache_name}") as cache:
        yield cache  # type: ignore


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
    > # True

    > result = is_pio_job_running(["od_reading", "stirring"])
    > # [True, False]
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


class SummableDict(dict):
    """
    SummableDict is a subclass of dict that allows for easy addition of two dictionaries by key.
    If a key exists in both dictionaries, the values are added together.
    If a key only exists in one dictionary, it is included in the result with its original value.

    Example
    ---------
    # create two SummableDicts
    d1 = SummableDict({'a': 1, 'b': 2})
    d2 = SummableDict({'b': 3, 'c': 4})

    # add them together
    result = d1 + d2

    # result should be {'a': 1, 'b': 5, 'c': 4}


    """

    def __init__(self, *arg, **kwargs):
        dict.__init__(self, *arg, **kwargs)

    def __add__(self, other):
        s = SummableDict()
        for key in self:
            s[key] += self[key]
        for key in other:
            s[key] += other[key]

        return s

    def __iadd__(self, other):
        return self + other

    def __getitem__(self, key):
        if key not in self:
            return 0
        else:
            return dict.__getitem__(self, key)


def retry(func: Callable, retries=3, delay=0.5, args=(), kwargs={}):
    """
    Retries a function upon encountering an exception until it succeeds or the maximum number of retries is exhausted.

    This function executes the provided function and handles any exceptions it raises. If an exception is raised,
    the function will wait for a specified delay before attempting to execute the function again. This process repeats
    until either the function execution is successful or the specified maximum number of retries is exhausted.
    On the final attempt, if the function still raises an exception, that exception will be re-raised to the caller.

    Parameters
    -----------
    func (callable): The function to be retried.
    retries (int, optional): The maximum number of times to retry the function. Defaults to 3.
    delay (float, optional): The number of seconds to wait between retries. Defaults to 0.5.
    args (tuple, optional): The positional arguments to pass to the function. Defaults to an empty tuple.
    kwargs (dict, optional): The keyword arguments to pass to the function. Defaults to an empty dictionary.

    Returns
    --------
    The return value of the function call, if the function call is successful.

    Raises
    --------
    Exception: The exception raised by the function call if the function call is unsuccessful after the specified number of retries.

    Example
    --------

    > def risky_function(x, y):
    >     return x / y
    >
    > # Call the function with retry
    > result = retry(risky_function, retries=5, delay=1, args=(10, 0))
    """
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == retries - 1:  # If this was the last attempt
                raise e
            time.sleep(delay)
