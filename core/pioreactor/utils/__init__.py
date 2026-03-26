# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import signal
import time
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from subprocess import run
from threading import Event
from typing import Any
from typing import Callable
from typing import cast
from typing import overload
from typing import Self
from typing import Sequence
from typing import TYPE_CHECKING

from msgspec import Struct
from pioreactor import structs
from pioreactor import types as pt
from pioreactor import whoami
from pioreactor.config import get_leader_hostname
from pioreactor.exc import JobRequiredError
from pioreactor.exc import NotActiveWorkerError
from pioreactor.exc import RoleError
from pioreactor.pubsub import create_client
from pioreactor.pubsub import patch_into
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.states import JobState as st
from pioreactor.utils.networking import resolve_to_address
from pioreactor.utils.signal_handlers import append_signal_handler
from pioreactor.utils.signal_handlers import append_signal_handlers
from pioreactor.utils.signal_handlers import callable_stack
from pioreactor.utils.signal_handlers import remove_signal_handler
from pioreactor.utils.signal_handlers import remove_signal_handlers
from pioreactor.utils.sqlite_cache import cache
from pioreactor.utils.sqlite_cache import local_intermittent_storage
from pioreactor.utils.sqlite_cache import local_persistent_storage
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_timestamp

if TYPE_CHECKING:
    from pioreactor.pubsub import Client


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
        mqtt_client: Client | None = None,
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
        self.state = st.INIT
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

        self.state = st.INIT
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
        self.state = st.READY
        self.publish_setting("$state", self.state)

        return self

    def __exit__(self, *args: object) -> None:
        self.state = st.DISCONNECTED
        self._exit()
        try:
            self.publish_setting("$state", self.state)
        finally:
            self._remove_passive_listeners()
            self._remove_signal_handlers()

            if not self._externally_provided_client:
                assert self.mqtt_client is not None
                self.mqtt_client.shutdown()

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
            _cleanup = self._mqtt_cleanup_callables.pop()
            _cleanup()

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
        mqtt_client: Client | None = None,
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


def clamp(minimum: float | int, x: float | int, maximum: float | int) -> float | int:
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
        for key, value in other.items():
            if key in self:
                self[key] = self[key] + value
            else:
                self[key] = value

        return self

    def __getitem__(self, key: Any) -> Any:
        if key not in self:
            return 0.0  # TODO: later could be generalized for the init to accept a zero element.
        else:
            return dict.__getitem__(self, key)


def boolean_retry(
    func: Callable[..., bool],
    retries: int = 3,
    sleep_for: float = 0.25,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
) -> bool:
    """
    Retries a function upon encountering an False return until it succeeds or the maximum number of retries is exhausted.

    """
    call_kwargs = {} if kwargs is None else kwargs
    for _ in range(retries):
        res = func(*args, **call_kwargs)
        if res:
            return res
        time.sleep(sleep_for)
    return False
