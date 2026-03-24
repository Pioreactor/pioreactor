# -*- coding: utf-8 -*-
import os
import signal
import sqlite3
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import wraps
from subprocess import run
from threading import Event
from typing import Any
from typing import Callable
from typing import cast
from typing import Generator
from typing import overload
from typing import Self
from typing import Sequence
from typing import TYPE_CHECKING

from msgspec import DecodeError
from msgspec import Struct
from msgspec.json import decode as loads
from msgspec.json import encode as dumps
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import config
from pioreactor.config import get_leader_hostname
from pioreactor.exc import JobRequiredError
from pioreactor.exc import NotActiveWorkerError
from pioreactor.exc import RoleError
from pioreactor.pubsub import create_client
from pioreactor.pubsub import patch_into
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.states import JobState as st
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_timestamp

if TYPE_CHECKING:
    from pioreactor.pubsub import Client


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

    def __init__(
        self,
        default_function_if_empty: Callable[..., None] = lambda *args: None,
        original_handler: Any = signal.SIG_DFL,
        call_original_handler_after_callbacks: bool = False,
    ) -> None:
        self._callables: list[Callable[..., None]] = []
        self.default = default_function_if_empty
        self.original_handler = original_handler
        self.call_original_handler_after_callbacks = call_original_handler_after_callbacks

    def append(self, function: Callable[..., None]) -> None:
        self._callables.append(function)

    def remove(self, function: Callable[..., None]) -> bool:
        for index in range(len(self._callables) - 1, -1, -1):
            if self._callables[index] == function:
                del self._callables[index]
                return True

        return False

    @property
    def is_empty(self) -> bool:
        return not self._callables

    def __call__(self, *args: object) -> None:
        if not self._callables:
            self.default(*args)
            return

        while self._callables:
            function = self._callables.pop()
            function(*args)

        if self.call_original_handler_after_callbacks and callable(self.original_handler):
            self.original_handler(*args)


def append_signal_handler(signal_value: signal.Signals, new_callback: Callable[..., None]) -> None:
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
            stack = callable_stack(
                signal.default_int_handler,
                original_handler=current_callback,
                call_original_handler_after_callbacks=True,
            )
            stack.append(new_callback)
            signal.signal(signal_value, stack)
    elif (current_callback is signal.SIG_DFL) or (current_callback is signal.SIG_IGN):
        # no stack yet.
        stack = callable_stack(signal.default_int_handler, original_handler=current_callback)
        stack.append(new_callback)
        signal.signal(signal_value, stack)
    elif current_callback is None:
        signal.signal(
            signal_value,
            callable_stack(signal.default_int_handler, original_handler=signal.SIG_DFL),
        )
    else:
        raise RuntimeError(f"Something is wrong. Observed {current_callback}.")


def append_signal_handlers(signal_value: signal.Signals, new_callbacks: list[Callable[..., None]]) -> None:
    for callback in new_callbacks:
        append_signal_handler(signal_value, callback)


def remove_signal_handler(signal_value: signal.Signals, callback_to_remove: Callable[..., None]) -> None:
    current_callback = signal.getsignal(signal_value)

    if not isinstance(current_callback, callable_stack):
        return

    current_callback.remove(callback_to_remove)

    if current_callback.is_empty:
        signal.signal(signal_value, current_callback.original_handler)
    else:
        signal.signal(signal_value, current_callback)


def remove_signal_handlers(
    signal_value: signal.Signals, callbacks_to_remove: list[Callable[..., None]]
) -> None:
    for callback in callbacks_to_remove:
        remove_signal_handler(signal_value, callback)


class managed_lifecycle:
    """
    Wrap a block of code to have "state" in MQTT and persistent cache. See od_normalization, self_test, pump

    You can use send a "disconnected" to "pioreactor/<unit>/<exp>/<name>/$state/set" to stop/disconnect it.

    Example
    ----------

    > with managed_lifecycle(unit, experiment, "self_test") as state: # publishes "ready" to mqtt
    >    value = do_work()
    >    state.publish_setting("work", value) # looks like a entry from a published_setting
    >
    > # on close of block, a "disconnected" is fired to MQTT, regardless of how that end is achieved (error, return statement, etc.)


    If the program is required to know if it's killed, managed_lifecycle contains an event (see pump.py code)

    > with managed_lifecycle(unit, experiment, "self_test") as state:
    >    do_work()
    >
    >    state.block_until_disconnected()
    >    # or state.exit_event.is_set() or state.exit_event.wait(...) are other options.
    >

    For now, it's possible to run multiple jobs with the same name using this tool.

    """

    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        name: str,
        mqtt_client: "Client | None" = None,
        exit_on_mqtt_disconnect: bool = False,
        mqtt_client_kwargs: dict[str, Any] | None = None,
        ignore_is_active_state: bool = False,  # hack and kinda gross
        is_long_running_job: bool = False,
        source: str = "app",
        job_source: str | None = None,
    ) -> None:
        if not ignore_is_active_state and not whoami.is_active(unit):
            raise NotActiveWorkerError(f"{unit} is not active.")

        self.unit = unit
        self.experiment = experiment
        self.name = name
        self.state = st("init")
        self.exit_event = Event()
        self._source = source
        self.is_long_running_job = is_long_running_job
        self._job_source = job_source or os.environ.get("JOB_SOURCE", "user")
        self._registered_signal_handlers = False
        self._mqtt_cleanup_callables: list[Callable[[], None]] = []

        try:
            # this only works on the main thread.
            append_signal_handlers(signal.SIGTERM, [self._exit])
            append_signal_handlers(
                signal.SIGINT, [self._exit]
            )  # ignore future sigints so we clean up properly.
            self._registered_signal_handlers = True
        except ValueError:
            pass

        from pioreactor.utils.job_manager import JobManager

        with JobManager() as jm:
            self.job_id = jm.register_and_set_running(
                self.unit,
                self.experiment,
                self.name,
                self._job_source,
                os.getpid(),
                get_leader_hostname(),
                self.is_long_running_job,
            )

        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.job_key}/$state",
            "payload": st.LOST.to_bytes(),
            "qos": 2,
            "retain": True,
        }

        default_mqtt_client_kwargs = {
            "keepalive": 5 * 60,
            "client_id": f"{self.job_key}-{self.unit}-{self.experiment}",
        }

        if mqtt_client is not None:
            self.mqtt_client = mqtt_client
            self._externally_provided_client = True
        else:
            self._externally_provided_client = False
            combined_mqtt_client_kwargs = cast(
                dict[str, Any],
                default_mqtt_client_kwargs | (mqtt_client_kwargs or {}),
            )
            self.mqtt_client = create_client(
                last_will=last_will,
                on_disconnect=self._on_disconnect if exit_on_mqtt_disconnect else None,
                **combined_mqtt_client_kwargs,
            )
        assert self.mqtt_client is not None

        self.state = st("init")
        self.publish_setting("$state", self.state)

        # Teardown for signal handlers and passive MQTT listeners is centralized in __exit__.
        # If construction fails after we register one of those resources but before the context
        # manager is entered, cleanup won't run automatically. We accept that initialization-time
        # leak risk for now, but it is a known failure mode of this lifecycle design.
        self.start_passive_listeners()

    @property
    def job_key(self) -> str:
        return self.name

    def _exit(self, *args: object) -> None:
        # recall: we can't publish in a callback!
        self.exit_event.set()

    def _on_disconnect(self, *args: object) -> None:
        self._exit()

    def __enter__(self) -> Self:
        self.state = st("ready")
        self.publish_setting("$state", self.state)

        return self

    def __exit__(self, *args: object) -> None:
        self.state = st("disconnected")
        self._exit()
        try:
            self.publish_setting("$state", self.state)
        finally:
            self._remove_passive_listeners()
            self._remove_signal_handlers()

            if not self._externally_provided_client:
                assert self.mqtt_client is not None
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()

            from pioreactor.utils.job_manager import JobManager

            with JobManager() as jm:
                jm.set_not_running(self.job_id)

        return

    def exit_from_mqtt(self, message: pt.MQTTMessage) -> None:
        if message.payload == st.DISCONNECTED.to_bytes():
            self._exit()

    def start_passive_listeners(self) -> None:
        subscribe_and_callback(
            self.exit_from_mqtt,
            [
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_key}/$state/set",
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_key}/$state/set",
                f"pioreactor/{whoami.UNIVERSAL_IDENTIFIER}/{whoami.UNIVERSAL_EXPERIMENT}/{self.job_key}/$state/set",
                f"pioreactor/{self.unit}/{whoami.UNIVERSAL_EXPERIMENT}/{self.job_key}/$state/set",
            ],
            client=self.mqtt_client,
            on_cleanup=self._mqtt_cleanup_callables,
        )
        return

    def _remove_passive_listeners(self) -> None:
        while self._mqtt_cleanup_callables:
            cleanup = self._mqtt_cleanup_callables.pop()
            cleanup()

    def _remove_signal_handlers(self) -> None:
        if not self._registered_signal_handlers:
            return

        remove_signal_handlers(signal.SIGTERM, [self._exit])
        remove_signal_handlers(signal.SIGINT, [self._exit])
        self._registered_signal_handlers = False

    def block_until_disconnected(self) -> None:
        self.exit_event.wait()

    def publish_setting(self, setting: str, value: Any) -> None:
        assert self.mqtt_client is not None
        self.mqtt_client.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_key}/{setting}", value, retain=True
        )
        from pioreactor.utils.job_manager import JobManager

        with JobManager() as jm:
            jm.upsert_setting(self.job_id, setting, value)


class long_running_managed_lifecycle(managed_lifecycle):
    def __init__(
        self,
        unit: pt.Unit,
        experiment: pt.Experiment,
        name: str,
        mqtt_client: "Client | None" = None,
        exit_on_mqtt_disconnect: bool = False,
        mqtt_client_kwargs: dict | None = None,
        source: str = "app",
        job_source: str | None = None,
    ) -> None:
        super().__init__(
            unit,
            experiment,
            name,
            is_long_running_job=True,
            ignore_is_active_state=True,
            mqtt_client=mqtt_client,
            exit_on_mqtt_disconnect=exit_on_mqtt_disconnect,
            mqtt_client_kwargs=mqtt_client_kwargs,
            source=source,
            job_source=job_source,
        )

    @property
    def job_key(self) -> str:
        # shitty proxy for "allow duplicate jobs", see #551
        # eventually, we will move all of mqtt topics to this format
        # the backslash here is deliberate and does change the mqtt topics
        if whoami.is_testing_env():
            return f"{self.name}/1"
        return f"{self.name}/{self.job_id}"


class cache:
    @staticmethod
    def adapt_key(key: object) -> bytes:
        # keys can be tuples!
        return dumps(key)

    @staticmethod
    def convert_key(s: str | bytes) -> object:
        def _restore_tuple_keys(value: object) -> object:
            if isinstance(value, list):
                return tuple(_restore_tuple_keys(item) for item in value)
            return value

        if isinstance(s, bytes):
            try:
                return _restore_tuple_keys(loads(s))
            except DecodeError:
                return s.decode()
        else:
            return s

    def __init__(self, table_name: str, db_path: str) -> None:
        self.table_name = f"cache_{table_name}"
        self.db_path = db_path

    def __enter__(self) -> Self:
        sqlite3.register_adapter(tuple, self.adapt_key)
        # sqlite3.register_converter("_key_BLOB", self.convert_key)

        self.conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, isolation_level=None, timeout=10
        )
        self.cursor = self.conn.cursor()
        self.cursor.executescript(
            """
            PRAGMA busy_timeout = 5000;
            PRAGMA temp_store = 2;
            PRAGMA cache_size = -4000;
        """
        )
        self._initialize_table()
        return self

    def __exit__(self, exc_type: object, exc_val: object, tb: object) -> None:
        self.conn.close()

    def _initialize_table(self) -> None:
        self.cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                key _key_BLOB PRIMARY KEY,
                value BLOB
            )
        """
        )

    def __setitem__(self, key: object, value: object) -> None:
        self.cursor.execute(
            f"""
            INSERT INTO {self.table_name} (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
            (key, value),
        )

    def set(self, key: object, value: object) -> None:
        return self.__setitem__(key, value)

    def set_if_absent(self, key: object, value: object) -> bool:
        self.cursor.execute(
            f"""
            INSERT OR IGNORE INTO {self.table_name} (key, value)
            VALUES (?, ?)
        """,
            (key, value),
        )
        return self.cursor.rowcount == 1

    def get(self, key: object, default: object = None) -> object:
        self.cursor.execute(f"SELECT value FROM {self.table_name} WHERE key = ?", (key,))
        result = self.cursor.fetchone()
        return result[0] if result else default

    def iterkeys(self) -> Generator[object, None, None]:
        self.cursor.execute(f"SELECT key FROM {self.table_name}")
        return (self.convert_key(row[0]) for row in self.cursor.fetchall())

    def pop(self, key: object, default: object = None) -> object:
        self.cursor.execute(f"DELETE FROM {self.table_name} WHERE key = ? RETURNING value", (key,))
        result = self.cursor.fetchone()

        if result is None:
            return default
        else:
            return result[0]

    def empty(self) -> None:
        self.cursor.execute(f"DELETE FROM {self.table_name}")

    def __contains__(self, key: object) -> bool:
        self.cursor.execute(f"SELECT 1 FROM {self.table_name} WHERE key = ?", (key,))
        return self.cursor.fetchone() is not None

    def __iter__(self) -> Generator[object, None, None]:
        return self.iterkeys()

    def __delitem__(self, key: object) -> None:
        self.cursor.execute(f"DELETE FROM {self.table_name} WHERE key = ?", (key,))

    def __getitem__(self, key: object) -> object:
        self.cursor.execute(f"SELECT value FROM {self.table_name} WHERE key = ?", (key,))
        result = self.cursor.fetchone()
        if result is None:
            raise KeyError(f"Key '{key}' not found in cache.")
        return result[0]


@contextmanager
def local_intermittent_storage(
    cache_name: str,
) -> Generator[cache, None, None]:
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
    with cache(cache_name, db_path=config.get("storage", "temporary_cache")) as c:
        yield c


@contextmanager
def local_persistent_storage(
    cache_name: str,
) -> Generator[cache, None, None]:
    """
    Values stored in this storage will stay around between RPi restarts, and until overwritten
    or deleted.

    Examples
    ---------
    > with local_persistent_storage('od_blank') as cache:
    >     assert '1' in cache
    >     cache['1'] = 0.5

    """

    with cache(cache_name, db_path=config.get("storage", "persistent_cache")) as c:
        yield c


def clamp(minimum: float | int, x: float | int, maximum: float | int) -> float:
    return max(minimum, min(x, maximum))


@overload
def is_pio_job_running(target_jobs: list[str]) -> list[bool]: ...


@overload
def is_pio_job_running(target_jobs: str) -> bool: ...


def is_pio_job_running(target_jobs: str | list[str]) -> bool | list[bool]:
    """
    pass in jobs to check if they are running
    ex:

    > result = is_pio_job_running("od_reading")
    > # True

    > result = is_pio_job_running(["od_reading", "stirring"])
    > # [True, False]
    """
    is_single_job_name = isinstance(target_jobs, str)
    if is_single_job_name:
        jobs_to_check: list[str] = [target_jobs]  # type: ignore[list-item]
    else:
        jobs_to_check = target_jobs  # type: ignore[assignment]

    results = []

    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        for job in jobs_to_check:
            results.append(jm.is_job_running(job))

    if is_single_job_name:
        return results[0]
    return results


def get_running_pio_job_id(job_name: str) -> int | None:
    """
    Return the running job_id for `job_name`, or None if not running.
    """
    from pioreactor.utils.job_manager import JobManager

    with JobManager() as jm:
        return jm.get_running_job_id(job_name)


def get_cpu_temperature() -> float:
    if whoami.is_testing_env():
        return 22.0

    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_temperature_celcius = int(f.read().strip()) / 1000.0
    except FileNotFoundError:
        return -999
    return cpu_temperature_celcius


def argextrema(x: Sequence[float | int]) -> tuple[int, int]:
    if len(x) == 0:
        raise ValueError("argextrema() arg is an empty sequence")

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

    # list values are concatenated
    d3 = SummableDict({'a': [1, 2]})
    d4 = SummableDict({'a': [3], 'b': [4]})
    result = d3 + d4
    # result should be {'a': [1, 2, 3], 'b': [4]}

    # also has a default value:
    print(result['missing_key']) # 0.0


    """

    def __init__(self, *arg: object, **kwargs: object) -> None:
        dict.__init__(self, *arg, **kwargs)

    def __add__(self, other: "SummableDict") -> "SummableDict":
        s = SummableDict()
        for key, value in self.items():
            s[key] = value
        for key, value in other.items():
            if key in s:
                s[key] = s[key] + value
            else:
                s[key] = value

        return s

    def __iadd__(self, other: "SummableDict") -> "SummableDict":
        return self + other

    def __getitem__(self, key: str) -> float:
        if key not in self:
            return 0.0  # TODO: later could be generalized for the init to accept a zero element.
        else:
            return dict.__getitem__(self, key)


def boolean_retry(
    func: Callable[..., bool],
    retries: int = 3,
    sleep_for: float = 0.25,
    args: tuple = (),
    kwargs: dict = {},
) -> bool:
    """
    Retries a function upon encountering an False return until it succeeds or the maximum number of retries is exhausted.

    """
    for _ in range(retries):
        res = func(*args, **kwargs)
        if res:
            return res
        time.sleep(sleep_for)
    return False
