# -*- coding: utf-8 -*-
from collections import namedtuple
from morbidostat.pubsub import subscribe_and_callback
from morbidostat import utils
from morbidostat.pubsub import publish, QOS
from typing import Optional, Union
from morbidostat.whoami import UNIVERSAL_IDENTIFIER


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
        self.verbose = verbose
        self.experiment = experiment
        self.unit = unit
        self.active = 1
        self.declare_settable_properties_to_broker()

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
                f"morbidostat/{self.unit}/{self.experiment}/{self.job}/{setting}/$settable",
                True,
                verbose=self.verbose,
                qos=QOS.AT_LEAST_ONCE,
            )

    def __setattr__(self, name: str, value: Union[int, str]) -> None:
        super(BackgroundJob, self).__setattr__(name, value)
        if (
            name in self.editable_settings and hasattr(self, name)
        ) or name == "active":  # TODO: clean this up; not sure why this is needed
            self.publish_attr(name)

    def set_attr_from_message(self, message):
        new_value = message.payload
        info_from_topic = split_topic_for_setting(message.topic)
        attr = info_from_topic.attr

        assert hasattr(self, attr), f"{self.job_name} has no attr {attr}."
        previous_value = getattr(self, attr)
        # make sure to cast the input to the same value
        setattr(self, attr, type(previous_value)(new_value))
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/log",
            f"[{self.job_name}] Updated {attr} from {previous_value} to {getattr(self, attr)}.",
            verbose=self.verbose,
        )

    def publish_attr(self, attr: str) -> None:
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
            getattr(self, attr),
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

    def start_passive_listeners(self) -> None:
        # also starts the last will
        last_will = {
            "topic": f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/active",
            "payload": 0,
            "qos": QOS.EXACTLY_ONCE,
            "retain": True,
        }

        subscribe_and_callback(
            self.set_attr_from_message,
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/+/set",
            will=last_will,
            qos=QOS.EXACTLY_ONCE,
        )

        # everyone listens to $unit
        subscribe_and_callback(
            self.set_attr_from_message,
            f"morbidostat/{UNIVERSAL_IDENTIFIER}/{self.experiment}/{self.job_name}/+/set",
            qos=QOS.EXACTLY_ONCE,
        )
