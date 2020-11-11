# -*- coding: utf-8 -*-
import signal
from typing import Optional, Union
import sys
from collections import namedtuple
from morbidostat.pubsub import subscribe_and_callback
from morbidostat import utils
from morbidostat.pubsub import publish, QOS
from morbidostat.whoami import UNIVERSAL_IDENTIFIER
from morbidostat.config import leader_hostname
import paho.mqtt.client as mqtt


def split_topic_for_setting(topic):
    SetAttrSplitTopic = namedtuple("SetAttrSplitTopic", ["unit", "experiment", "job_name", "attr"])
    v = topic.split("/")
    assert len(v) == 6, "something is wrong"
    return SetAttrSplitTopic(v[1], v[2], v[3], v[4])


class BackgroundJob:

    """
    This class handles the fanning out of class attributes, and the setting of those attributes. Use
    `morbidostat/<unit>/<experiment>/<job_name>/<attr>/set` to set an attribute.

    `publish_out` is a list  of variables that will be sent to the broker on initialization and retained.

    """

    editable_settings = []

    def __init__(self, job_name: str, verbose: int = 0, experiment: Optional[str] = None, unit: Optional[str] = None) -> None:
        self.job_name = job_name
        self.experiment = experiment
        self.verbose = verbose
        self.unit = unit
        self.editable_settings = self.editable_settings + ["state"]

        self.init()
        self.ready()

    def init(self):

        signal.signal(signal.SIGTERM, self.catch_kill_signal)
        signal.signal(signal.SIGINT, self.catch_kill_signal)

        self.state = "init"
        self.set_will()
        self.declare_settable_properties_to_broker()
        self.start_general_passive_listeners()

    def ready(self):
        self.state = "ready"

    def sleeping(self):
        self.state = "sleeping"

    def disconnected(self):
        self.state = "disconnected"
        self._client.disconnect()

        for attr in self.editable_settings:
            if attr == "state":
                continue

            publish(
                f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                None,
                verbose=self.verbose,
                qos=QOS.AT_LEAST_ONCE,
            )

        sys.exit()

    def declare_settable_properties_to_broker(self):
        # this follows some of the Homie convention: https://homieiot.github.io/specification/
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/$properties",
            ",".join(self.editable_settings),
            verbose=self.verbose,
            qos=QOS.AT_LEAST_ONCE,
        )

        for setting in self.editable_settings:
            publish(
                f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{setting}/$settable",
                True,
                verbose=self.verbose,
                qos=QOS.AT_LEAST_ONCE,
            )

    def set_state(self, new_state):
        getattr(self, new_state)()

    def set_attr_from_message(self, message):

        new_value = message.payload.decode()
        info_from_topic = split_topic_for_setting(message.topic)
        attr = info_from_topic.attr

        if attr == "$state":
            return self.set_state(new_value)

        if attr not in self.editable_settings:
            return

        assert hasattr(self, attr), f"{self.job_name} has no attr {attr}."
        previous_value = getattr(self, attr)

        try:
            # make sure to cast the input to the same value
            setattr(self, attr, type(previous_value)(new_value))
        except:
            setattr(self, attr, new_value)

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/log",
            f"[{self.job_name}] Updated {attr} from {previous_value} to {getattr(self, attr)}.",
            verbose=self.verbose,
        )

    def publish_attr(self, attr: str) -> None:
        if attr == "state":
            attr_name = "$state"
        else:
            attr_name = attr

        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr_name}",
            getattr(self, attr),
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

    def start_general_passive_listeners(self) -> None:

        subscribe_and_callback(
            self.set_attr_from_message, f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/+/set", qos=QOS.EXACTLY_ONCE
        )

        # everyone listens to $unit
        subscribe_and_callback(
            self.set_attr_from_message,
            f"morbidostat/{UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_name}/+/set",
            qos=QOS.EXACTLY_ONCE,
        )

    def set_will(self):
        last_will = {
            "topic": f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/$state",
            "payload": "lost",
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }
        self._client = mqtt.Client()
        self._client.connect(leader_hostname)
        self._client.will_set(**last_will)

    def catch_kill_signal(self, *args):
        self.set_state("disconnected")

    def __setattr__(self, name: str, value: Union[int, str]) -> None:
        super(BackgroundJob, self).__setattr__(name, value)
        if (name in self.editable_settings) and hasattr(self, name):
            self.publish_attr(name)
