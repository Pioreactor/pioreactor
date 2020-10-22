# -*- coding: utf-8 -*-
from morbidostat.pubsub import subscribe_and_callback
from morbidostat import utils
from morbidostat.pubsub import publish, QOS


class BackgroundJob:

    """
    This class handles the fanning out of class attributes, and the setting of those attributes. Use
    `morbidostat/<unit>/<experiment>/<job_name>/<attr>/set` to set an attribute.

    `publish_out` is a list  of variables that will be sent to the broker on initialization and retained.

    """

    publish_out = []

    def __init__(self, job_name, verbose=0, experiment=None, unit=None):
        self.job_name = job_name
        self.verbose = verbose
        self.experiment = experiment
        self.unit = unit
        self.active = 1
        self.publish_initialized_attrs()
        self.set_currently_active_and_last_will()

    def set_attr(self, message):
        new_value = message.payload
        info_from_topic = utils.split_topic_for_setting(message.topic)
        attr = info_from_topic.attr

        assert hasattr(self, attr), f"{self.job_name} has no attr {attr}."
        previous_value = getattr(self, attr)
        # make sure to cast the input to the same value
        setattr(self, attr, type(previous_value)(new_value))
        self.publish_attr(attr)

    def publish_initialized_attrs(self):
        for attr in self.publish_out:
            if hasattr(self, attr):
                self.publish_attr(attr)

    def publish_attr(self, attr):
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
            getattr(self, attr),
            verbose=self.verbose,
            retain=True,
            qos=QOS.EXACTLY_ONCE,
        )

    def set_currently_active_and_last_will(self):
        topic = f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/active"
        last_will = {"topic": topic, "payload": 0, "qos": QOS.EXACTLY_ONCE, "retain": True}
        publish(topic, 1, qos=QOS.EXACTLY_ONCE, will=last_will, retain=True)

    def start_passive_listeners(self):
        subscribe_and_callback(self.set_attr, f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/+/set")
