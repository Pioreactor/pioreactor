# -*- coding: utf-8 -*-
import signal
import os
import time
import sys
import threading
import atexit
from collections import namedtuple
import logging

from pioreactor.pubsub import subscribe_and_callback
from pioreactor.utils import pio_jobs_running
from pioreactor.pubsub import publish, QOS
from pioreactor.whoami import UNIVERSAL_IDENTIFIER


def split_topic_for_setting(topic):
    SetAttrSplitTopic = namedtuple(
        "SetAttrSplitTopic", ["unit", "experiment", "job_name", "attr"]
    )
    v = topic.split("/")
    assert len(v) == 6, "something is wrong"
    return SetAttrSplitTopic(v[1], v[2], v[3], v[4])


class BackgroundJob:

    """
    This class handles the fanning out of class attributes, and the setting of those attributes. Use
    `pioreactor/<unit>/<experiment>/<job_name>/<attr>/set` to set an attribute.


    So this class controls most of the Homie convention that we follow:

    1. The device lifecycle: init -> ready -> disconnect (or lost).
        1. The job starts in `init`, where we publish `editable_settings` is a list  of variables that will be sent
            to the broker on initialization and retained.
        2. The job moves to `ready`.
        3. We catch key interrupts and kill signals from the underlying machine, and set the state to
           `disconnected`. This should not empty the attributes, since they may be needed upon node restart.
        4. If the job exits otherwise (kill -9 or power loss), the state is `lost`, and a last-will saying so is broadcast.
    2. Attributes are broadcast under $properties, and each has $settable set to True. This isn't used at the moment.

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
    editable_settings = []

    def __init__(self, job_name: str, experiment=None, unit=None) -> None:
        self.job_name = job_name
        self.experiment = experiment
        self.unit = unit
        self.editable_settings = self.editable_settings + ["state"]
        self.pubsub_clients = []
        self.logger = logging.getLogger(self.job_name)

        self.check_for_duplicate_process()
        self.set_state(self.INIT)
        self.set_state(self.READY)

    def init(self):
        self.state = self.INIT
        self.logger.info(self.INIT)

        def disconnect_gracefully(*args):
            if self.state == self.DISCONNECTED:
                return

            self.set_state("disconnected")

        def exit_python(*args):
            # this is for race conflicts - without it was causing the MQTT client to disconnect wrong and a last-will was sent.
            time.sleep(1)
            sys.exit(0)

        # signals only work in main thread - and if we set state via MQTT,
        # this runs in a thread
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, disconnect_gracefully)
            signal.signal(signal.SIGINT, disconnect_gracefully)
            signal.signal(signal.SIGUSR1, exit_python)
            atexit.register(disconnect_gracefully)

        # if we re-init (via MQTT, close previous threads)
        for client in self.pubsub_clients:
            client.loop_stop()  # pretty sure this doesn't close the thread if called in a thread: https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L1835
            client.disconnect()

        self.pubsub_clients = []

        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()

    def ready(self):
        self.state = self.READY
        self.logger.info(self.READY)

    def sleeping(self):
        self.state = self.SLEEPING
        self.logger.info(self.SLEEPING)

    def on_disconnect(self):
        # specific things to do when a job disconnects / exits
        pass

    def disconnected(self):
        # call job specific on_disconnect to clean up subjobs, etc.
        self.on_disconnect()

        # disconnect from the passive subscription threads
        for client in self.pubsub_clients:
            client.loop_stop()  # pretty sure this doesn't close the thread if if in a thread: https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L1835
            client.disconnect()

        # set state to disconnect
        self.state = self.DISCONNECTED
        self.logger.info(self.DISCONNECTED)
        # exit from python using a signal - this works in threads (sometimes `disconnected` is called in a thread)
        os.kill(os.getpid(), signal.SIGUSR1)

    def declare_settable_properties_to_broker(self):
        # this follows some of the Homie convention: https://homieiot.github.io/specification/
        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$properties",
            ",".join(self.editable_settings),
            qos=QOS.AT_LEAST_ONCE,
        )

        for setting in self.editable_settings:
            publish(
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{setting}/$settable",
                True,
                qos=QOS.AT_LEAST_ONCE,
            )

    def set_state(self, new_state):
        assert new_state in self.LIFECYCLE_STATES, f"saw {new_state}: not a valid state"
        getattr(self, new_state)()

    def set_attr_from_message(self, message):

        new_value = message.payload.decode()
        info_from_topic = split_topic_for_setting(message.topic)
        attr = info_from_topic.attr.lstrip("$")

        if attr not in self.editable_settings:
            return

        assert hasattr(self, attr), f"{self.job_name} has no attr {attr}."
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

        self.logger.info(
            f"Updated {attr} from {previous_value} to {getattr(self, attr)}."
        )

    def publish_attr(self, attr: str) -> None:
        if attr == "state":
            attr_name = "$state"
        else:
            attr_name = attr

        publish(
            f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/{attr_name}",
            getattr(self, attr),
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

    def start_general_passive_listeners(self) -> None:

        last_will = {
            "topic": f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/$state",
            "payload": self.LOST,
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        # listen to changes in editable properties
        # everyone listens to $BROADCAST (TODO: even leader?)
        client = subscribe_and_callback(
            self.set_attr_from_message,
            [
                f"pioreactor/{self.unit}/{self.experiment}/{self.job_name}/+/set",
                f"pioreactor/{UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_name}/+/set",
            ],
            qos=QOS.EXACTLY_ONCE,
            last_will=last_will,
            job_name=self.job_name,
            keepalive=20,  # slightly lower than the default 60, as we want to know quickly when the client has failed / broke
        )
        client.name = "test"
        self.pubsub_clients.append(client)

    def check_for_duplicate_process(self):
        if (
            sum([p == self.job_name for p in pio_jobs_running()]) > 1
        ):  # this process counts as one - see if there is another.
            self.logger.error(f"Aborting: {self.job_name} is already running.")
            raise ValueError(f"Another {self.job_name} is running on machine. Aborting.")

    def __setattr__(self, name: str, value) -> None:
        super(BackgroundJob, self).__setattr__(name, value)
        if (name in self.editable_settings) and hasattr(self, name):
            self.publish_attr(name)
