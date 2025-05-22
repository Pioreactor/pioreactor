# -*- coding: utf-8 -*-
from __future__ import annotations

import atexit
import signal
import threading
import typing as t
from copy import copy
from os import environ
from os import getpid
from time import sleep
from time import time

from msgspec.json import decode as loads
from msgspec.json import encode as dumps

from pioreactor import structs
from pioreactor import types as pt
from pioreactor.config import config
from pioreactor.config import leader_hostname
from pioreactor.exc import NotActiveWorkerError
from pioreactor.logging import create_logger
from pioreactor.pubsub import Client
from pioreactor.pubsub import create_client
from pioreactor.pubsub import QOS
from pioreactor.utils import append_signal_handlers
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import JobManager
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import is_active
from pioreactor.whoami import is_testing_env
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


T = t.TypeVar("T")
BJT = t.TypeVar("BJT", bound="_BackgroundJob")

# these are used elsewhere in our software
DISALLOWED_JOB_NAMES = {
    "run",
    "dosing_events",
    "leds",
    "led_change_events",
    "unit_label",
    "pwm",
}


def cast_bytes_to_type(value: bytes, type_: str) -> t.Any:
    try:
        if type_ == "string":
            return value.decode()
        elif type_ == "float":
            return float(value)
        elif type_ == "integer":
            return int(value)
        elif type_ == "boolean":
            return value.decode().lower() in ("true", "1", "y", "on", "yes")
        elif type_ == "json":
            return loads(value)
        elif type_ == "Automation":
            return loads(value, type=structs.AnyAutomation)  # type: ignore
        raise TypeError(f"{type_} not found.")
    except Exception as e:
        raise e


def format_with_optional_units(value: pt.PublishableSettingDataType, units: t.Optional[str]) -> str:
    """
    Ex:
    > format_with_optional_units(25.0, "cm") # returns "25.0 cm"
    > format_with_optional_units(25.0, None) # returns "25.0"
    > format_with_optional_units("some_very_long_string___", None) # returns "some_very_long_stri..."
    """
    max_ = 40

    if units is None:
        s = f"{value}"
    elif units == "%":
        s = f"{value}{units}"
    else:
        s = f"{value} {units}"

    return s[:max_] + (s[max_:] and "..")


class LoggerMixin:
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._logger = None

    def add_external_logger(self, logger) -> None:
        self._logger = logger

    @property
    def logger(self):
        if self._logger is None:
            self._logger = create_logger(name=self._logger_name or self.__class__.__name__)
        return self._logger

    def __del__(self):
        if self._logger:
            self._logger.clean_up()


class PostInitCaller(type):
    def __call__(cls, *args, **kwargs):
        obj = type.__call__(cls, *args, **kwargs)
        obj.__post__init__()
        return obj


class _BackgroundJob(metaclass=PostInitCaller):

    """
    State management & hooks
    ---------------------------

    So this class controls most of the state convention that we follow (states inspired by Homie):

                                        ┌──────────┐
                                        │          │
         ┌──────────────────────┬───────►   lost   ◄────────┐
         │                      │       │          │        │
         │                      │       └─────▲────┘        │
         │                      │             │             │
    ┌────┴─────┐          ┌─────┴──────┐      │     ┌───────┴──────┐
    │          │          │            │      │     │              │
    │   init   ├──────────►    ready   ├──────┼─────► disconnected │
    │          │          │            │      │     │              │
    └──────────┘          └────┬──▲────┘      │     └──────▲───────┘
                               │  │           │            │
                               │  │           │            │
                               │  │           │            │
                          ┌────▼──┴────┬──────┘            │
                          │            │                   │
                          │  sleeping  ├───────────────────┘
                          │            │
                          └────────────┘

    https://asciiflow.com/#/share/eJzNVEsKgzAQvYrM2lW7Uc%2BSjehQAmksmoIi3qJ4kC7F0%2FQkTS0tRE0crYuGWWSEeZ95wRpkfEaI5FUIH0RcYQ4R1AxKBlEYhD6DSt8OwVHfFJZKNww8wnnc%2BsViTBKhjOYzRqHYXm2nKURWqBdT2xFsGDrnDYytzLsioEzVjr5sQ7b2GoOyNWOGWCbn2pzewizaR0bmyCab%2BAJyyRVJ0PBSvBzjtFphQE%2BlvEgyKTFRmBrU%2B3rZIzXL%2B3Kn1t4dqXn2M6Cafqbu%2FxxicYHUSBZpHC0VoBCIFy5PP%2F9TV%2Bgkb87BBg00T7Hk%2FaY%3D)

    states-mermaid-diagram
        init --> ready
        init --> lost
        ready --> lost
        ready --> disconnected
        ready --> sleeping
        sleeping --> ready
        sleeping --> lost
        sleeping --> disconnected
        disconnected --> lost


    1. The job starts in `init`,
        - we publish `published_settings`: a list of variables that will be sent to the broker on initialization and retained.
        - we set up how to disconnect
        - the subclass runs their __init__ method
    2. The job moves to `ready`, and can be paused by entering `sleeping`.
    3. We catch key interrupts and kill signals from the underlying machine, and set the state to `disconnected`.
    4. If the job exits otherwise (kill -9, power loss, bug), the state is `lost`, and a last-will saying so is broadcast.

    When changing state, it's recommend to use `set_state(new_state)`.

    When going from state S to state T, a function `on_{S}_to_{T}` is called, and then a
    function `on_{T}` is called. These can be overwritten in subclasses for specific usecases (ex: sleeping should turn off a motor,
    and  going from sleeping to ready should restart the motor.)


    Editing properties
    ---------------------

    This class handles the fanning out of class attributes, and the setting of those attributes. Use
    `pioreactor/<unit>/<experiment>/<job_name>/<attr>/set` to set an attribute remotely.

    Hooks can be set up when property `p` changes. The function `set_p(self, new_value)`
    will be called (if defined) whenever `p` changes over MQTT.

    Best code practices of background jobs
    ---------------------------------------

    Because of the setup, connections, and tear downs of background jobs, the best practices of using
    background jobs is as follows:

    1. Use context managers

    > with Stirrer(duty_cycle=50, unit=unit, experiment=experiment) as stirrer:
    >     stirrer.start_stirring()
    >     ...
    >

    This will gracefully disconnect and cleanup the job, provided you clean up in the `on_disconnected` function.

    2. Clean up yourself. The following is **not** recommended as it does not cleanup connections and state even after the function exits:

    > def do_some_stirring():
    >     st = Stirrer(duty_cycle=50, unit=unit, experiment=experiment)
    >     return

    Instead do something like:

    > def do_some_stirring():
    >     st = Stirrer(duty_cycle=50, unit=unit, experiment=experiment)
    >     ...
    >     st.clean_up()
    >     return

    When Python exits, jobs will also clean themselves up, so this also works as a script:

    > if __name__ == "__main__":
    >    st = Stirrer(...)
    >

    If you want the script to pause until the job disconnects, use

    > if __name__ == "__main__":
    >    st = Stirrer(...)
    >
    >    st.block_until_disconnected()
    >



    Parameters
    -----------

    job_name: str
        the name of the job
    source: str
        the source of where this job lives. "app" if main code base, <plugin name> if from a plugin, etc. This is used in logging.
    experiment: str
    unit: str
    """

    # Homie lifecycle (normally per device (i.e. an rpi) but we are using it for "nodes", in Homie parlance)
    INIT: pt.JobState = "init"
    READY: pt.JobState = "ready"
    DISCONNECTED: pt.JobState = "disconnected"
    SLEEPING: pt.JobState = "sleeping"
    LOST: pt.JobState = "lost"

    # initial state is disconnected, set other metadata
    state = DISCONNECTED
    job_name = "background_job"  # this should be overwritten in subclasses
    _is_cleaned_up = False  # mqtt connections closed, JM cache is empty, logger closed, etc.
    _IS_LONG_RUNNING = False  # by default, jobs aren't long running (persistent over experiments)

    # published_settings is typically overwritten in the subclasses. Attributes here will
    # be published to MQTT and available settable attributes will be editable. Currently supported
    # attributes are
    # {'datatype', 'unit', 'settable', 'persist'}
    # See pt.PublishableSetting type
    published_settings: dict[str, pt.PublishableSetting] = dict()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        orig_init = cls.__init__

        def wrapped_init(self, *args, **kwargs):
            try:
                orig_init(self, *args, **kwargs)
            except Exception:
                try:
                    self.clean_up()
                except Exception:
                    pass
                raise

        cls.__init__ = wrapped_init

    def __init__(self, unit: str, experiment: str, source: str = "app") -> None:
        if self.job_name in DISALLOWED_JOB_NAMES:
            raise ValueError("Job name not allowed.")
        if not self.job_name.islower():
            raise ValueError("Job name should be all lowercase.")

        self.experiment = experiment
        self.unit = unit
        self._source = source
        self._job_source = environ.get(
            "JOB_SOURCE", default="user"
        )  # ex: could be JOB_SOURCE=experiment_profile, or JOB_SOURCE=external_provider.

        # why do we need two clients? Paho lib can't publish a message in a callback,
        # but this is critical to our usecase: listen for events, and fire a response (ex: state change)
        # so we split the listening and publishing. I've tried combining them and got stuck a lot
        # https://github.com/Pioreactor/pioreactor/blob/cb54974c9be68616a7f4fb45fe60fdc063c81238/pioreactor/background_jobs/base.py
        # See issue: https://github.com/eclipse/paho.mqtt.python/issues/527
        # The order we add them to the list is important too, as disconnects occur async,
        # we want to give the sub_client (has the will msg) as much time as possible to disconnect.
        self.pub_client = self._create_pub_client()

        self.logger = create_logger(
            self.job_name,
            unit=self.unit,
            experiment=self.experiment,
            source=self._source,
            pub_client=self.pub_client,
        )

        self._check_for_duplicate_activity()

        self.job_id = self._add_to_job_manager()

        # if we no-op in the _check_for_duplicate_activity, we don't want to fire the LWT, so we delay subclient until after.
        self.sub_client = self._create_sub_client()

        # add state
        self.published_settings = self.published_settings | {
            "state": {
                "datatype": "string",
                "settable": True,
                "persist": True,
            }
        }

        # this comes _after_ adding state to published settings
        self.set_state(self.INIT)

        self._set_up_exit_protocol()
        self._blocking_event = threading.Event()

        try:
            # this is one function in the __init__ that we may deliberately raise an error
            # if we do raise an error, the class needs to be cleaned up correctly
            # (hence the _cleanup bit, don't use set_state)
            # but we still raise the error afterwards.
            self._check_published_settings(self.published_settings)

        except ValueError as e:
            self.logger.debug(e, exc_info=True)
            self.logger.error(e)
            self._clean_up_resources()
            raise e

        # this should happen _after_ pub clients are set up
        self._start_general_passive_listeners()

        # next thing that run is the subclasses __init__

    def __post__init__(self) -> None:
        """
        This function is called AFTER the subclass' __init__ finishes successfully

        Typical sequence (doesn't represent calling stack, but "blocks of code" run)

        P == BackgroundJob (this class)
        C == calling class (a subclass)

        P.__init__() # check for duplicate job, among other checks
        C.__init__() # Note: risk of job failing here
        P.__post__init__()  # THIS FUNCTION
        P.on_init_to_ready()  # default noop - can be overwritten in sub class C
        P.ready()
        C.on_ready() # default noop
        """
        # setting READY should happen after we write to the job manager, since a job might do a long-running
        # task in on_ready, which delays writing to the db, which means `pio kill` might not see it.
        self.set_state(self.READY)

    def start_passive_listeners(self) -> None:
        # overwrite this to in subclasses to subscribe to topics in MQTT
        # using this handles reconnects correctly.
        pass

    # subclasses to override these to perform certain actions on a state transfer
    def on_ready(self) -> None:
        # specific things to do when is ready (again)
        pass

    def on_init(self) -> None:
        # Note: this is called after this classes __init__, but before the subclasses __init__
        pass

    def on_sleeping(self) -> None:
        # specific things to do when a job sleeps / pauses
        pass

    def on_disconnected(self) -> None:
        # specific things to do when a job disconnects / exits
        pass

    def on_disconnected_to_ready(self) -> None:
        pass

    def on_ready_to_disconnected(self) -> None:
        pass

    def on_disconnected_to_sleeping(self) -> None:
        pass

    def on_sleeping_to_disconnected(self) -> None:
        pass

    def on_disconnected_to_init(self) -> None:
        pass

    def on_init_to_disconnected(self) -> None:
        pass

    def on_ready_to_sleeping(self) -> None:
        pass

    def on_sleeping_to_ready(self) -> None:
        pass

    def on_ready_to_init(self) -> None:
        pass

    def on_init_to_ready(self) -> None:
        pass

    def on_sleeping_to_init(self) -> None:
        pass

    def on_init_to_sleeping(self) -> None:
        pass

    def publish(
        self,
        topic: str,
        payload: pt.PublishableSettingDataType | dict | bytes | None,
        qos: int = QOS.EXACTLY_ONCE,
        **kwargs,
    ) -> None:
        """
        Publish payload to topic.

        This will convert the payload to a json blob if MQTT does not allow its original type.
        """

        if not isinstance(payload, (str, bytearray, bytes, int, float)) and (payload is not None):
            payload = dumps(payload)

        self.pub_client.publish(topic, payload=payload, **kwargs)

    def subscribe_and_callback(
        self,
        callback: t.Callable[[pt.MQTTMessage], None],
        subscriptions: list[str] | str,
        allow_retained: bool = True,
        qos: int = QOS.EXACTLY_ONCE,
    ) -> None:
        """
        Parameters
        -------------
        callback: callable
            Callbacks only accept a single parameter, message.
        subscriptions: str, list of str
        allow_retained: bool
            if True, all messages are allowed, including messages that the broker has retained. Note
            that client can fire a msg with retain=True, but because the broker is serving it to a
            subscriber "fresh", it will have retain=False on the client side. More here:
            https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L364
        qos: int
            see pioreactor.pubsub.QOS
        """

        def wrap_callback(actual_callback: t.Callable[..., T]) -> t.Callable[..., t.Optional[T]]:
            def _callback(client, userdata, message: pt.MQTTMessage) -> t.Optional[T]:
                if not allow_retained and message.retain:
                    return None
                try:
                    return actual_callback(message)
                except Exception as e:
                    self.logger.error(e)
                    self.logger.debug(e, exc_info=True)
                    raise e

            return _callback

        assert callable(
            callback
        ), "callback should be callable - do you need to change the order of arguments?"

        subscriptions = [subscriptions] if isinstance(subscriptions, str) else subscriptions

        for topic in subscriptions:
            self.sub_client.message_callback_add(str(topic), wrap_callback(callback))
            self.sub_client.subscribe(str(topic), qos=qos)
        return

    def set_state(self, new_state: pt.JobState) -> None:
        """
        The preferred way to change states is to use this function (instead of self.state = state). Note:

         - no-op if in the same state
         - will call the transition callback

        """

        if new_state not in {self.INIT, self.READY, self.DISCONNECTED, self.SLEEPING, self.LOST}:
            self.logger.error(f"saw {new_state}: not a valid state")
            return

        if new_state == self.state:
            return

        if hasattr(self, f"on_{self.state}_to_{new_state}"):
            try:
                getattr(self, f"on_{self.state}_to_{new_state}")()
            except Exception as e:
                self.logger.debug(f"Error in on_{self.state}_to_{new_state}")
                self.logger.debug(e, exc_info=True)
                self.logger.error(e)
                return

        getattr(self, new_state)()

    def block_until_disconnected(self) -> None:
        """
        This will block the main thread until disconnected() is called.

        This will unblock if:

        1. a kill/keyboard interrupt signal is sent
        2. state is set to "disconnected" over MQTT or programmatically

        Useful for standalone jobs (and with click). Ex:

        > if __name__ == "__main__":
        >     job = Job(...)
        >     job.block_until_disconnected()


        """
        self.logger.debug(f"{self.job_name} is blocking until disconnected.")
        self._blocking_event.wait()

    def blink_error_code(self, error_code: int) -> None:
        """
        Publish the error code to `monitor` job s.t. it will make the Pioreactor blink.
        See pioreactor.error_codes
        """
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/monitor/flicker_led_with_error_code",
            error_code,
        )

    def clean_up(self) -> None:
        """
        Disconnect from brokers, set state to "disconnected", stop any activity.
        """
        if self.state != self.DISCONNECTED:
            self.set_state(self.DISCONNECTED)
        self._clean_up_resources()

    def add_to_published_settings(self, setting: str, props: pt.PublishableSetting) -> None:
        """
        Add a pair to self.published_settings.
        """
        new_setting_pair = {setting: props}
        self._check_published_settings(new_setting_pair)
        # we need create a new dict (versus just a key update), since published_settings is a class level prop, and editing this would have effects for other BackgroundJob classes.
        self.published_settings = self.published_settings | new_setting_pair

    ########### Private #############

    @staticmethod
    def _check_published_settings(published_settings: dict[str, pt.PublishableSetting]) -> None:
        necessary_properies = {"datatype", "settable"}
        optional_properties = {"unit", "persist"}
        all_properties = optional_properties.union(necessary_properies)
        for setting, properties in published_settings.items():
            # look for extra properties
            if not all_properties.issuperset(properties.keys()):
                raise ValueError(f"Found extra property in setting `{setting}`.")

            # look for missing properties
            if not set(properties.keys()).issuperset(necessary_properies):
                raise ValueError(
                    f"Missing necessary property in setting `{setting}`. All settings require at least {necessary_properies}"
                )

            # correct syntax in setting name?
            if not all(ss.isalnum() for ss in setting.split("_")):
                # only alphanumeric separated by _ is allowed.
                raise ValueError(
                    f"setting {setting} has bad characters - must be alphanumeric, and only separated by underscore."
                )

    def _create_pub_client(self) -> Client:
        # see note above as to why we split pub and sub.
        client = create_client(
            client_id=f"{self.job_name}-pub-{self.unit}-{self.experiment}",
            keepalive=15 * 60,
        )

        return client

    def _create_sub_client(self) -> Client:
        # see note above as to why we split pub and sub.

        # we give the last_will to this sub client because when it reconnects, it
        # will republish state.
        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$state",
            "payload": self.LOST,
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        # the client will try to automatically reconnect if something bad happens
        # when we reconnect to the broker, we want to republish our state
        # also reconnect to our old topics (see reconnect_protocol)
        # before we connect, we also want to set a new last_will (in case the existing one
        # was exhausted), so we reset the last will in the pre_connect callback.
        def set_last_will(client: Client, userdata) -> None:
            # we can only set last wills _before_ connecting, so we put this here.
            client.will_set(**last_will)  # type: ignore

        def reconnect_protocol(client: Client, userdata, flags, rc: int, properties=None) -> None:
            self.logger.info("Sub client reconnected to the MQTT broker on leader.")
            self._publish_defined_settings_to_broker(self.published_settings)
            self._start_general_passive_listeners()
            self.start_passive_listeners()

        def on_disconnect(client, userdata, flags, reason_code, properties) -> None:
            self._on_mqtt_disconnect(client, reason_code)

        client = create_client(
            client_id=f"{self.job_name}-sub-{self.unit}-{self.experiment}",
            last_will=last_will,
            keepalive=125,
            clean_session=False,  # this, in theory, will reconnect to old subs when we reconnect.
        )
        # we catch exceptions and report them in our software
        client.suppress_exceptions = True

        # the client connects async, but we want it to be connected before adding
        # our reconnect callback
        for _ in range(200):
            if not client.is_connected():
                sleep(0.01)
            else:
                break

        # these all are assigned _after_ connection is made:
        client.on_pre_connect = set_last_will
        client.on_connect = reconnect_protocol
        client.on_disconnect = on_disconnect
        return client

    def _on_mqtt_disconnect(self, client: Client, reason_code: int) -> None:
        from paho.mqtt.enums import MQTTErrorCode as mqtt
        from paho.mqtt.client import error_string

        if reason_code == mqtt.MQTT_ERR_SUCCESS:
            # MQTT_ERR_SUCCESS means that the client disconnected using disconnect()
            self.logger.debug("Disconnected successfully from MQTT.")

        # we won't exit, but the client object will try to reconnect
        # Error codes are below, but don't always align
        # https://github.com/eclipse/paho.mqtt.python/blob/42f0b13001cb39aee97c2b60a3b4807314dfcb4d/src/paho/mqtt/client.py#L147
        elif reason_code == mqtt.MQTT_ERR_KEEPALIVE:
            self.logger.warning("Lost contact with MQTT server. Is the leader Pioreactor still online?")
        else:
            self.logger.debug(f"Disconnected from MQTT with {reason_code=}: {error_string(reason_code)}")
        return

    def _publish_setting(self, setting: str) -> None:
        """
        Publish the current value of the class attribute `attr` to MQTT.
        """
        if setting == "state":
            setting_name = "$state"
        else:
            setting_name = setting
        value = getattr(self, setting)

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting_name}",
            value,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )
        with JobManager() as jm:
            jm.upsert_setting(self.job_id, setting_name, value)

    def _set_up_exit_protocol(self) -> None:
        # here, we set up how jobs should disconnect and exit.
        def exit_gracefully(reason: int | str, *args) -> None:
            if self._is_cleaned_up:
                return

            if isinstance(reason, int):
                self.logger.debug(f"Exiting caused by signal {signal.strsignal(reason)}.")
            elif isinstance(reason, str):
                self.logger.debug(f"Exiting caused by {reason}.")

            self.clean_up()

            if (reason == signal.SIGTERM) or (reason == getattr(signal, "SIGHUP", None)):
                # wait for threads to clean up
                sleep(1)

                import sys

                sys.exit()
            return

        # signals only work in main thread - and if we set state via MQTT,
        # this would run in a thread - so just skip.
        if threading.current_thread() is threading.main_thread():
            atexit.register(exit_gracefully, "Python atexit")

            # terminate command, ex: pkill, kill
            append_signal_handlers(signal.SIGTERM, [exit_gracefully])

            # keyboard interrupt
            append_signal_handlers(
                signal.SIGINT,
                [exit_gracefully],
            )

            try:
                # ssh closes
                append_signal_handlers(
                    signal.SIGHUP,
                    [
                        exit_gracefully,
                        # add a "ignore all future SIGUPs" onto the top of the stack.
                        lambda *args: signal.signal(signal.SIGHUP, signal.SIG_IGN),
                    ],
                )
            except AttributeError:
                # SIGHUP is only available on unix machines
                pass

    def init(self) -> None:
        self.state = self.INIT

        try:
            # we delay the specific on_init until after we have done our important protocols.
            self.on_init()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)
            self.clean_up()
            raise e

        self._log_state(self.state)

    def ready(self) -> None:
        self.state = self.READY

        try:
            self.on_ready()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug("Error in on_ready:")
            self.logger.debug(e, exc_info=True)

        self._log_state(self.state)

    def sleeping(self) -> None:
        self.state = self.SLEEPING

        try:
            self.on_sleeping()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug("Error in on_sleeping:")
            self.logger.debug(e, exc_info=True)

        self._log_state(self.state)

    def lost(self) -> None:
        # TODO: what should happen when a running job receives a lost signal? When does it ever
        # receive a lost signal?
        # 1. Monitor can send a lost signal if `check_against_processes_running` triggers.
        # I think it makes sense to ignore it?

        self.state = self.LOST
        self._log_state(self.state)

    def disconnected(self) -> None:
        # call job specific on_disconnected to clean up subjobs, etc.
        # however, if it fails, nothing below executes, so we don't get a clean
        # disconnect, etc.
        # ideally, the on_disconnected shouldn't care what state it was in prior to being called.
        try:
            self.on_disconnected()
        except Exception as e:
            # since on_disconnected errors are common (see point below), we don't bother
            # making the visible to the user.
            # They are common when the user quickly starts a job then stops a job.
            self.logger.debug("Error in on_disconnected:")
            self.logger.debug(e, exc_info=True)

        self.state = self.DISCONNECTED
        self._log_state(self.state)

        # we "set" the internal event, which will cause any event.waits to end blocking. This should happen last.
        self._blocking_event.set()

    def _remove_from_job_manager(self) -> None:
        # TODO what happens if the job_id isn't found?
        if hasattr(self, "job_id"):
            with JobManager() as jm:
                jm.set_not_running(self.job_id)

    def _add_to_job_manager(self) -> int:
        # this registration use to be in post_init, and I feel like it was there for a good reason...
        with JobManager() as jm:
            return jm.register_and_set_running(
                self.unit,
                self.experiment,
                self.job_name,
                self._job_source,
                getpid(),
                leader_hostname,
                self._IS_LONG_RUNNING,
            )

    def _disconnect_from_loggers(self) -> None:
        # clean up logger handlers
        self.logger.clean_up()

    def _disconnect_from_mqtt_clients(self) -> None:
        # disconnect from MQTT
        self.sub_client.loop_stop()
        self.sub_client.disconnect()

        # this HAS to happen last, because this contains our publishing client
        self.pub_client.loop_stop()  # pretty sure this doesn't close the thread if in a thread: https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L1835
        self.pub_client.disconnect()

    def _clean_up_resources(self) -> None:
        self._clear_caches()
        self._remove_from_job_manager()
        self._disconnect_from_mqtt_clients()
        self._disconnect_from_loggers()

        self._is_cleaned_up = True

    def _publish_defined_settings_to_broker(
        self, published_settings: dict[str, pt.PublishableSetting]
    ) -> None:
        for name in published_settings.keys():
            if hasattr(self, name):
                self._publish_setting(name)

    def _log_state(self, state: pt.JobState) -> None:
        if state == self.READY or state == self.DISCONNECTED:
            self.logger.info(state.capitalize() + ".")
        else:
            self.logger.debug(state.capitalize() + ".")

    def _set_attr_from_message(self, message: pt.MQTTMessage) -> None:
        def get_attr_from_topic(topic: str) -> str:
            pieces = topic.split("/")
            return pieces[4].lstrip("$")

        attr = get_attr_from_topic(message.topic)

        if attr not in self.published_settings:
            self.logger.debug(f"Unable to set `{attr}` in {self.job_name}.")
            return
        elif not self.published_settings[attr]["settable"]:
            self.logger.warning(f"Unable to set `{attr}` in {self.job_name}. `{attr}` is read-only.")
            return

        if not hasattr(self, attr):
            # for some reason, the attr isn't on the object yet. Could be a race condition, or the author forgot something.
            self.logger.debug(f"attribute `{attr}` is not a property of {self}.")
            return

        previous_value = copy(getattr(self, attr))
        new_value = cast_bytes_to_type(message.payload, self.published_settings[attr]["datatype"])

        # a subclass may want to define a `set_<attr>` method that will be used instead
        # for example, see Stirring.set_target_rpm, and `set_state` here
        if hasattr(self, f"set_{attr}"):
            getattr(self, f"set_{attr}")(new_value)
        else:
            setattr(self, attr, new_value)

        units = self.published_settings[attr].get("unit")
        self.logger.info(
            f"Updated {attr} from {format_with_optional_units(previous_value, units)} to {format_with_optional_units(getattr(self, attr), units)}."
        )

    def _start_general_passive_listeners(self) -> None:
        # listen to changes in editable properties
        self.subscribe_and_callback(
            self._set_attr_from_message,
            [
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/+/set",
                # everyone listens to $BROADCAST
                f"pioreactor/{UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_name}/+/set",
            ],
            allow_retained=False,
        )

        # TODO: previously this was in __post_init__ - why?
        # now start listening to confirm our state is correct in mqtt
        self.subscribe_and_callback(
            self._confirm_state_in_broker,
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$state",
        )

    def _confirm_state_in_broker(self, message: pt.MQTTMessage) -> None:
        if message.payload is None:
            return

        state_in_broker = message.payload.decode()
        if state_in_broker == self.LOST and state_in_broker != self.state:
            self.logger.debug(
                f"Job is in state {self.state}, but in state {state_in_broker} in broker. Attempting fix by publishing {self.state}."
            )
            sleep(5)
            self._publish_setting("state")

    @property
    def job_key(self):
        # not used...yet
        return self.job_name + "/" + self.job_id

    def _clear_caches(self) -> None:
        """
        From homie: Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics.
        Use "persist" to keep it from clearing.
        """

        # iterate twice since publish and upsert_setting are slow, and I don't want to block the db.
        for setting, metadata_on_attr in self.published_settings.items():
            if not metadata_on_attr.get("persist", False):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting}",
                    None,
                    retain=True,
                )

        with JobManager() as jm:
            for setting, metadata_on_attr in self.published_settings.items():
                if not metadata_on_attr.get("persist", False):
                    jm.upsert_setting(self.job_id, setting, None)

    def _check_for_duplicate_activity(self) -> None:
        if is_pio_job_running(self.job_name) and not is_testing_env():
            self.logger.warning(f"{self.job_name} is already running. Skipping.")
            raise RuntimeError(f"{self.job_name} is already running. Skipping.")

    def __setattr__(self, name: str, value: t.Any) -> None:
        super(_BackgroundJob, self).__setattr__(name, value)
        if name in self.published_settings:
            self._publish_setting(name)

    def __enter__(self: BJT) -> BJT:
        return self

    def __exit__(self, *args) -> None:
        self.clean_up()


class LongRunningBackgroundJob(_BackgroundJob):
    """
    This doesn't check for is_active and doesn't obey `pio kill --all-jobs` so should be used for jobs like monitor, etc.
    """

    _IS_LONG_RUNNING = True

    def __init__(self, unit: str, experiment: str) -> None:
        super().__init__(unit, experiment, source="app")


class LongRunningBackgroundJobContrib(_BackgroundJob):
    """
    Used for jobs like logs2x, etc.
    """

    _IS_LONG_RUNNING = True

    def __init__(self, unit: str, experiment: str, plugin_name: str) -> None:
        super().__init__(unit, experiment, source=plugin_name)


class BackgroundJob(_BackgroundJob):
    """
    Worker jobs should inherit from this class.
    """

    def __init__(self, unit: str, experiment: str) -> None:
        if not is_active(unit):
            raise NotActiveWorkerError(
                f"{unit} is not active. Make active in leader, or set ACTIVE=1 in the environment: ACTIVE=1 pio run ... "
            )
        super().__init__(unit, experiment, source="app")


class BackgroundJobContrib(_BackgroundJob):
    """
    Plugin jobs should inherit from this class.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.job_name == "background_job":
            raise NameError(f"must provide a job_name property to this BackgroundJob class {cls}.")

    def __init__(self, unit: str, experiment: str, plugin_name: str) -> None:
        super().__init__(unit, experiment, source=plugin_name)


def _noop():
    pass


class BackgroundJobWithDodging(_BackgroundJob):
    """
    This utility class allows for a change in behaviour when an OD reading is about to taken. Example: shutting
    off a air-bubbler, or shutting off an LED, with appropriate delay between.

    The methods `action_to_do_before_od_reading` and `action_to_do_after_od_reading` need to be overwritten, and
    optional initialize_dodging_operation and initialize_continuous_operation can be overwritten.

    If dodging is enabled, and OD reading is present then:
      1. initialize_dodging_operation runs immediately. Use this to set up important state for dodging
      2. before an OD reading is taken, action_to_do_before_od_reading is run
      3. after an OD reading is taken, action_to_do_after_od_reading is run
    If dodging is enabled, but OD reading is not present OR dodging is NOT enabled:
      1. initialize_continuous_operation runs immediately. Use this to set up important state for continuous operation.

    Config parameters needs to be added:

        [<job_name>.config]
        post_delay_duration=
        pre_delay_duration=
        enable_dodging_od=True
        ...

    Example
    ------------


        class JustPause(BackgroundJobWithDodging):
            job_name="just_pause"

            def __init__(self, unit, experiment):
                super().__init__(unit=unit, experiment=experiment)

            def action_to_do_before_od_reading(self):
                self.logger.debug("Pausing")

            def action_to_do_after_od_reading(self):
                self.logger.debug("Unpausing")

        start_od_reading("90", "REF", interval=5, fake_data=True)

        job = JustPause("test", "test")
        job.block_until_disconnected()

    """

    OD_READING_DURATION = (
        1.0  # WARNING: this may change slightly in the future, don't depend on this too much.
    )
    sneak_in_timer: RepeatedTimer
    currently_dodging_od = False

    def __init__(self, *args, source="app", **kwargs) -> None:
        super().__init__(*args, source=source, **kwargs)  # type: ignore

        if not config.has_section(f"{self.job_name}.config"):
            self.logger.error(
                f"Required section '{self.job_name}.config' does not exist in the configuration."
            )
            raise ValueError(
                f"Required section '{self.job_name}.config' does not exist in the configuration."
            )

        self.sneak_in_timer = RepeatedTimer(
            5, _noop, job_name=self.job_name, logger=self.logger
        )  # placeholder?
        self.add_to_published_settings("enable_dodging_od", {"datatype": "boolean", "settable": True})
        self.add_to_published_settings("currently_dodging_od", {"datatype": "boolean", "settable": False})
        self._event_is_dodging_od = threading.Event()

    def __post__init__(self):
        # this method runs after the subclasses init
        self.set_enable_dodging_od(
            config.getboolean(f"{self.job_name}.config", "enable_dodging_od", fallback="False")
        )
        # now that `enable_dodging_od` is set, we can check for OD changes
        self.subscribe_and_callback(
            self._od_reading_changed_status,
            f"pioreactor/{self.unit}/{self.experiment}/od_reading/interval",
            allow_retained=False,  # only allow future changes
        )
        super().__post__init__()  # set ready

    def set_currently_dodging_od(self, value: bool):
        self.currently_dodging_od = value
        if self.currently_dodging_od:
            self._event_is_dodging_od.clear()
            self.initialize_dodging_operation()  # user defined
            self._action_to_do_before_od_reading = self.action_to_do_before_od_reading
            self._action_to_do_after_od_reading = self.action_to_do_after_od_reading
            self._setup_timer()
        else:
            self._event_is_dodging_od.set()
            self.sneak_in_timer.cancel()
            self.initialize_continuous_operation()  # user defined
            self._action_to_do_before_od_reading = _noop
            self._action_to_do_after_od_reading = _noop

    def set_enable_dodging_od(self, value: bool):
        self.enable_dodging_od = value
        if self.enable_dodging_od:
            if is_pio_job_running("od_reading"):
                self.logger.debug("Will attempt to dodge OD readings.")
                self.set_currently_dodging_od(True)
            else:
                self.logger.debug("Will attempt to dodge OD readings when they start.")
                self.set_currently_dodging_od(False)
        else:
            if is_pio_job_running("od_reading"):
                self.logger.debug("Running continuously through OD readings.")
            self.set_currently_dodging_od(False)

    def action_to_do_after_od_reading(self) -> None:
        pass

    def action_to_do_before_od_reading(self) -> None:
        pass

    def initialize_dodging_operation(self) -> None:
        pass

    def initialize_continuous_operation(self) -> None:
        pass

    def _od_reading_changed_status(self, msg: pt.MQTTMessage) -> None:
        if self.enable_dodging_od:
            # only act if our internal state is discordant with the external state
            if msg.payload and not self.currently_dodging_od:
                # turned off
                self.logger.debug("OD reading present. Dodging!")
                self.set_currently_dodging_od(True)
            elif not msg.payload and self.currently_dodging_od:
                self.logger.debug("OD reading turned off. Stop dodging.")
                self.set_currently_dodging_od(False)
            return
        else:
            # ignore
            return

    def _setup_timer(self) -> None:
        self.sneak_in_timer.cancel()

        post_delay = config.getfloat(f"{self.job_name}.config", "post_delay_duration", fallback=0.5)
        pre_delay = config.getfloat(f"{self.job_name}.config", "pre_delay_duration", fallback=1.5)

        if post_delay < 0.25:
            self.logger.warning("For optimal OD readings, keep `post_delay_duration` more than 0.25 seconds.")

        if pre_delay < 0.25:
            self.logger.warning("For optimal OD readings, keep `pre_delay_duration` more than 0.25 seconds.")

        def sneak_in(ads_interval: float, post_delay: float, pre_delay: float) -> None:
            if self.state != self.READY or not self.currently_dodging_od:
                return

            with catchtime() as timer:
                self._action_to_do_after_od_reading()

            action_after_duration = timer()

            if ads_interval - self.OD_READING_DURATION - (post_delay + pre_delay) - action_after_duration < 0:
                raise ValueError(
                    "samples_per_second is too high, or post_delay is too high, or pre_delay is too high, or action_to_do_after_od_reading takes too long."
                )

            if self.state != self.READY or not self.currently_dodging_od:
                return

            self._event_is_dodging_od.wait(
                ads_interval - self.OD_READING_DURATION - (post_delay + pre_delay) - action_after_duration
            )  # we use an Event here to allow for quick stopping of the timer.

            if self.state != self.READY or not self.currently_dodging_od:
                return

            self._action_to_do_before_od_reading()

        # this could fail in the following way:
        # in the same experiment, the od_reading fails catastrophically so that the settings are never
        # cleared. Later, this job starts, and it will pick up the _old_ settings.
        with JobManager() as jm:
            ads_interval = float(jm.get_setting_from_running_job("od_reading", "interval", timeout=5))
            ads_start_time = float(
                jm.get_setting_from_running_job("od_reading", "first_od_obs_time", timeout=5)
            )  # this is populated later in the OD job...

        # get interval, and confirm that the requirements are possible: post_delay + pre_delay <= ADS interval - (od reading duration)
        if not (ads_interval - self.OD_READING_DURATION > (post_delay + pre_delay)):
            self.logger.error(
                f"Your {pre_delay=} or {post_delay=} is too high for the samples_per_second={1/ads_interval}. Either decrease pre_delay or post_delay, or decrease samples_per_second"
            )
            self.clean_up()

        time_to_next_ads_reading = ads_interval - ((time() - ads_start_time) % ads_interval)

        self.sneak_in_timer = RepeatedTimer(
            ads_interval,
            sneak_in,
            job_name=self.job_name,
            args=(ads_interval, post_delay, pre_delay),
            run_immediately=True,
            run_after=time_to_next_ads_reading + (post_delay + self.OD_READING_DURATION),
            logger=self.logger,
        )
        self.sneak_in_timer.start()

    def on_sleeping(self) -> None:
        try:
            self._event_is_dodging_od.set()
            self.sneak_in_timer.pause()
        except AttributeError:
            pass

    def on_disconnected(self) -> None:
        try:
            self._event_is_dodging_od.set()
            self.sneak_in_timer.cancel()
        except AttributeError:
            pass

    def on_sleeping_to_ready(self) -> None:
        try:
            self._event_is_dodging_od.clear()
            self.sneak_in_timer.unpause()
        except AttributeError:
            pass


class BackgroundJobWithDodgingContrib(BackgroundJobWithDodging):
    """
    Plugin jobs should inherit from this class.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.job_name == "background_job":
            raise NameError(f"must provide a job_name property to this BackgroundJob class {cls}.")

    def __init__(self, unit: str, experiment: str, plugin_name: str) -> None:
        super().__init__(unit=unit, experiment=experiment, source=plugin_name)
