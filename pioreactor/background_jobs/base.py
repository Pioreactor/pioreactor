# -*- coding: utf-8 -*-
import signal
import os
import sys
import threading
import atexit
from collections import namedtuple
from json import dumps

from pioreactor.utils import pio_jobs_running, local_intermittent_storage
from pioreactor.pubsub import QOS, create_client
from pioreactor.whoami import UNIVERSAL_IDENTIFIER, is_testing_env
from pioreactor.logging import create_logger


def split_topic_for_setting(topic):
    SetAttrSplitTopic = namedtuple(
        "SetAttrSplitTopic", ["unit", "experiment", "job_name", "attr"]
    )
    v = topic.split("/")
    assert len(v) == 6, "something is wrong"
    return SetAttrSplitTopic(v[1], v[2], v[3], v[4])


def format_with_optional_units(value, units):
    """
    Ex:
    > format_with_optional_units(25.0, "cm") # returns "25.0 cm"
    > format_with_optional_units(25.0, None) # returns "25.0"
    """
    if units is not None:
        return f"{value} {units}"
    else:
        return f"{value}"


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
                                ┌───────►   lost   ◄────────┐
                                │       │          │        │
                                │       └─────▲────┘        │
                                │             │             │
    ┌──────────┐          ┌─────┴──────┐      │     ┌───────┴──────┐
    │          │          │            │      │     │              │
    │   init   ├──────────►   ready    ├──────┼─────► disconnected │
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

    On __init__, attributes are broadcast under `pioreactor/<unit>/<experiment>/<job_name>/$properties`,
    and each has
     - `pioreactor/<unit>/<experiment>/<job_name>/$settable` set to True or False
     - `pioreactor/<unit>/<experiment>/<job_name>/$datatype` set to its datatype
     - `pioreactor/<unit>/<experiment>/<job_name>/$unit` set to its unit (optional)


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
    INIT = "init"
    READY = "ready"
    DISCONNECTED = "disconnected"
    SLEEPING = "sleeping"
    LOST = "lost"
    LIFECYCLE_STATES = {INIT, READY, DISCONNECTED, SLEEPING, LOST}

    # initial state is disconnected
    state = DISCONNECTED

    # published_settings is typically overwritten in the subclasses. Attributes here will
    # be published to MQTT and available settable attributes will be editable. Currently supported
    # attributes are
    # {'datatype', 'units', 'settable'}
    published_settings = dict()

    def __init__(
        self, job_name: str, source: str, experiment: str = None, unit: str = None
    ):

        self.job_name = job_name
        self.experiment = experiment
        self.unit = unit
        self.sub_jobs = []
        self.published_settings["state"] = {"datatype": "string", "settable": True}

        self.logger = create_logger(
            self.job_name,
            unit=self.unit,
            experiment=self.experiment,
            source=source
            # TODO: the following should work, but doesn't. When we disconnect a subjob, like when changing dosing_automations,
            # the new subjob does _not_ log anything to MQTT - it's like the logger is still using the (disconnected) subjobs pub_client.
            # For now, we will just create a new client each time.
            # pub_client=self.pub_client,
        )

        # check_for_duplicate_process needs to come _before_ the pubsub client,
        # as they will set (and revoke) a new last will.
        # Ex: job X is running, but we try to rerun it, causing the latter job to abort, and
        # potentially firing the last_will
        self.check_for_duplicate_process()

        # why do we need two clients? Paho lib can't publish a message in a callback,
        # but this is critical to our usecase: listen for events, and fire a response (ex: state change)
        # so we split the listening and publishing. I've tried combining them and got stuck a lot
        # https://github.com/Pioreactor/pioreactor/blob/cb54974c9be68616a7f4fb45fe60fdc063c81238/pioreactor/background_jobs/base.py
        # See issue: https://github.com/eclipse/paho.mqtt.python/issues/527
        # The order we add them to the list is important too, as disconnects occur async,
        # we want to give the sub_client (has the will msg) as much time as possible to disconnect.
        self.pub_client = self.create_pub_client()
        self.sub_client = self.create_sub_client()
        self.pubsub_clients = [self.sub_client, self.pub_client]

        self.set_up_exit_protocol()
        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()

        # let's move to init, next thing that run is the subclasses __init__
        self.set_state(self.INIT)

    def __post__init__(self):
        # this function is called AFTER the subclasses __init__ finishes
        self.set_state(self.READY)

    def start_passive_listeners(self):
        # overwrite this to in subclasses to subscribe to topics in MQTT
        # using this handles reconnects correctly.
        pass

    # subclasses to override these to perform certain actions on a state transfer
    def on_ready(self):
        # specific things to do when is ready (again)
        pass

    def on_init(self):
        # Note: this is called after this classes __init__, but before the subclasses __init__
        pass

    def on_sleeping(self):
        # specific things to do when a job sleeps / pauses
        pass

    def on_disconnect(self):
        # specific things to do when a job disconnects / exits
        pass

    def on_disconnected_to_ready(self):
        pass

    def on_ready_to_disconnected(self):
        pass

    def on_disconnected_to_sleeping(self):
        pass

    def on_sleeping_to_disconnected(self):
        pass

    def on_disconnected_to_init(self):
        pass

    def on_init_to_disconnected(self):
        pass

    def on_ready_to_sleeping(self):
        pass

    def on_sleeping_to_ready(self):
        pass

    def on_ready_to_init(self):
        pass

    def on_init_to_ready(self):
        pass

    def on_sleeping_to_init(self):
        pass

    def on_init_to_sleeping(self):
        pass

    ########### private #############

    def create_pub_client(self):
        # see note above as to why we split pub and sub.
        client = create_client(client_id=f"{self.unit}-pub-{self.job_name}-{id(self)}")

        return client

    def create_sub_client(self):
        # see note above as to why we split pub and sub.

        # the client will try to automatically reconnect if something bad happens
        # when we reconnect to the broker, we want to republish our state
        # to overwrite potential last-will losts...
        # also reconnect to our old topics.
        def reconnect_protocol(client, userdata, flags, rc, properties=None):
            self.logger.debug("Reconnected to MQTT broker.")
            self.publish_attr("state")
            self.start_general_passive_listeners()
            self.start_passive_listeners()

        def on_disconnect(client, userdata, rc):

            self.on_mqtt_disconnect(rc)

        # we give the last_will to this sub client because when it reconnects, it
        # will republish state.
        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$state",
            "payload": self.LOST,
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        client = create_client(
            client_id=f"{self.unit}-sub-{self.job_name}-{id(self)}",
            last_will=last_will,
            keepalive=20,
        )
        # we catch exceptions and report them in our software
        client.suppress_exceptions = True

        # the client connects async, but we want it to be connected before adding
        # our reconnect callback
        while not client.is_connected():
            continue

        client.on_connect = reconnect_protocol
        client.on_disconnect = on_disconnect
        return client

    def on_mqtt_disconnect(self, rc):
        if (
            rc == 0
        ):  # MQTT_ERR_SUCCESS means that the client disconnected using disconnect()
            self.logger.debug("Disconnected successfully from MQTT.")
            os.kill(os.getpid(), signal.SIGUSR1)

        else:
            # we won't exit, but the client object will try to reconnect
            # Error codes are below, but don't always align
            # https://github.com/eclipse/paho.mqtt.python/blob/42f0b13001cb39aee97c2b60a3b4807314dfcb4d/src/paho/mqtt/client.py#L147
            self.logger.debug(f"Disconnected from MQTT with rc {rc}.")
            return

    def publish(self, topic, payload, **kwargs):
        """
        Publish payload to topic.

        This will convert the payload to a json blob if MQTT does not allow its original type.
        """

        if not isinstance(payload, (str, bytearray, int, float)) and (
            payload is not None
        ):
            payload = dumps(payload)

        self.pub_client.publish(topic, payload=payload, **kwargs)

    def publish_attr(self, attr: str) -> None:
        """
        Publish the current value of the class attribute `attr` to MQTT.
        """
        if attr == "state":
            attr_name = "$state"
        else:
            attr_name = attr

        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr_name}",
            getattr(self, attr),
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

    def subscribe_and_callback(self, callback, subscriptions, allow_retained=True, qos=0):
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

        def wrap_callback(actual_callback):
            def _callback(client, userdata, message):
                if not allow_retained and message.retain:
                    return
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

        subscriptions = (
            [subscriptions] if isinstance(subscriptions, str) else subscriptions
        )

        for sub in subscriptions:
            self.sub_client.message_callback_add(sub, wrap_callback(callback))
            self.sub_client.subscribe(sub, qos=qos)
        return

    def set_up_exit_protocol(self):
        # here, we set up how jobs should disconnect and exit.
        def disconnect_gracefully(*args):
            # ignore future keyboard interrupts
            signal.signal(signal.SIGINT, lambda *args: None)
            if self.state == self.DISCONNECTED:
                return
            self.set_state(self.DISCONNECTED)

        def is_interactive():
            import __main__ as main

            return not hasattr(main, "__file__")

        def exit_python(*args):
            # don't exit in test mode
            # don't kill yourself if in a shell like `python3` or `ipython`
            if is_testing_env() or is_interactive():
                return
            else:
                sys.exit(0)

        # signals only work in main thread - and if we set state via MQTT,
        # this would run in a thread - so just skip.
        if threading.current_thread() is threading.main_thread():
            atexit.register(disconnect_gracefully)

            # terminate command, ex: pkill
            signal.signal(signal.SIGTERM, disconnect_gracefully)

            # keyboard interrupt
            signal.signal(signal.SIGINT, disconnect_gracefully)

            # NOHUP is not included here, as it prevents tools like nohup working: https://unix.stackexchange.com/a/261631

            # user defined signal, we use to exit
            signal.signal(signal.SIGUSR1, exit_python)

    def init(self):
        self.state = self.INIT
        self.log_state(self.state)

        try:
            # we delay the specific on_init until after we have done our important protocols.
            self.on_init()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)

    def ready(self):
        self.state = self.READY
        self.log_state(self.state)

        try:
            self.on_ready()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)

    def sleeping(self):
        self.state = self.SLEEPING
        self.log_state(self.state)

        try:
            self.on_sleeping()
        except Exception as e:
            self.logger.error(e)
            self.logger.debug(e, exc_info=True)

    def lost(self):
        self.state = self.LOST
        self.log_state(self.state)

    def disconnected(self):
        # set state to disconnect
        # call this first to make sure that it gets published to the broker.
        self.state = self.DISCONNECTED
        self.log_state(self.state)
        # if a job exits ungracefully, we log the error here (possibly a duplication...)
        # this is a partial resolution to issue #145
        if hasattr(sys, "last_traceback"):
            import traceback

            self.logger.debug("".join(traceback.format_tb(sys.last_traceback)))
            self.logger.error(sys.last_value)

        # call job specific on_disconnect to clean up subjobs, etc.
        # however, if it fails, nothing below executes, so we don't get a clean
        # disconnect, etc.
        # ideally, the on_disconnect shouldn't care what state it was in prior to being called.
        try:
            self.on_disconnect()  # TODO: shouldn't this be is_disconnected
        except Exception as e:
            # since on_disconnected errors are common (see point below), we don't bother
            # making the visible to the user.
            # They are common when the user quickly starts a job then stops a job.
            self.logger.debug(e, exc_info=True)

        with local_intermittent_storage("pio_jobs_running") as cache:
            cache[self.job_name] = b"0"

        # this HAS to happen last, because this contains our publishing client
        for client in self.pubsub_clients:
            client.loop_stop()  # pretty sure this doesn't close the thread if in a thread: https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L1835
            client.disconnect()

        # a disconnect callback calls sys.exit(), so no code below will run.

    def declare_settable_properties_to_broker(self):
        # this follows some of the Homie convention: https://homieiot.github.io/specification/
        self.publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$properties",
            ",".join(self.published_settings),
            qos=QOS.AT_LEAST_ONCE,
        )

        for setting, props in self.published_settings.items():
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting}/$settable",
                props["settable"],
                qos=QOS.AT_LEAST_ONCE,
            )
            self.publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting}/$datatype",
                props["datatype"],
                qos=QOS.AT_LEAST_ONCE,
            )
            if props.get("unit"):
                self.publish(
                    f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting}/$unit",
                    props["unit"],
                    qos=QOS.AT_LEAST_ONCE,
                )

    def set_state(self, new_state):
        assert new_state in self.LIFECYCLE_STATES, f"saw {new_state}: not a valid state"

        if hasattr(self, f"on_{self.state}_to_{new_state}"):
            getattr(self, f"on_{self.state}_to_{new_state}")()

        getattr(self, new_state)()

    def log_state(self, state):
        if state == self.READY or state == self.DISCONNECTED:
            self.logger.info(state.capitalize() + ".")
        else:
            self.logger.debug(state.capitalize() + ".")

    def set_attr_from_message(self, message):

        new_value = message.payload.decode()
        info_from_topic = split_topic_for_setting(message.topic)
        attr = info_from_topic.attr.lstrip("$")

        if not (
            (attr in self.published_settings)
            and (self.published_settings[attr]["settable"])
        ):
            self.logger.debug(f"Unable to set {attr} in {self.job_name}.")
            return

        previous_value = getattr(self, attr)

        # a subclass may want to define a `set_<attr>` method that will be used instead
        # for example, see Stirring, and `set_state` here
        if hasattr(self, "set_%s" % attr):
            getattr(self, "set_%s" % attr)(new_value)

        else:
            try:
                # make sure to cast the input to the same value
                setattr(self, attr, type(previous_value)(new_value))
            except TypeError:
                setattr(self, attr, new_value)

        units = self.published_settings[attr].get("unit")
        self.logger.info(
            f"Updated {attr} from {format_with_optional_units(previous_value, units)} to {format_with_optional_units(getattr(self, attr), units)}."
        )

    def start_general_passive_listeners(self) -> None:
        # listen to changes in editable properties
        self.subscribe_and_callback(
            self.set_attr_from_message,
            [
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/+/set",
                # everyone listens to $BROADCAST
                f"pioreactor/{UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_name}/+/set",
            ],
            allow_retained=False,
        )

    def check_for_duplicate_process(self):

        with local_intermittent_storage("pio_jobs_running") as cache:
            if cache.get(self.job_name, b"0") == b"1":
                # double check using psutils
                if (
                    sum([p == self.job_name for p in pio_jobs_running()]) > 1
                ):  # this process counts as one - see if there is another.
                    self.logger.warning(f"{self.job_name} is already running. Aborting.")
                    raise ValueError(f"{self.job_name} is already running. Aborting.")

            cache[self.job_name] = b"1"

    def __setattr__(self, name: str, value) -> None:
        super(_BackgroundJob, self).__setattr__(name, value)
        if (name in self.published_settings) and hasattr(self, name):
            self.publish_attr(name)

    def __exit__(self):
        self.disconnected()


class BackgroundJob(_BackgroundJob):
    def __init__(self, *args, **kwargs):
        super(BackgroundJob, self).__init__(*args, **kwargs, source="app")


class BackgroundJobContrib(_BackgroundJob):
    """
    Plugins should inherit from this class.
    """

    def __init__(self, plugin_name, *args, **kwargs):
        super(BackgroundJobContrib, self).__init__(*args, **kwargs, source=plugin_name)
