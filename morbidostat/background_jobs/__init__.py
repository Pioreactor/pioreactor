# -*- coding: utf-8 -*-
from morbidostat.pubsub import subscribe_and_callback
from morbidostat import utils
from morbidostat.pubsub import publish


class BackgroundJob:

    publish_out = []

    def __init__(self, job_name, verbose=0, experiment=None, unit=None):
        self.job_name = job_name
        self.verbose = verbose
        self.experiment = experiment
        self.unit = unit
        self.publish_initialized_attrs()

    def set_attr(self, message):
        new_value = message.payload
        info_from_topic = utils.split_topic_for_setting(message.topic)
        attr = info_from_topic.attr

        assert hasattr(self, attr), f"{self.job_name} has no attr {attr}."
        previous_value = getattr(self, attr)
        # make sure to cast the input to the same value
        setattr(self, attr, type(previous_value)(new_value))
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/log",
            f"Updated {self.job_name}.{attr} from {previous_value} to {getattr(self, attr)}.",
            verbose=self.verbose,
        )
        publish(
            f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
            getattr(self, attr),
            verbose=self.verbose,
            retain=True,
        )

    def publish_initialized_attrs(self):
        for attr in self.publish_out:
            if hasattr(self, attr):
                publish(
                    f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/{attr}",
                    getattr(self, attr),
                    verbose=self.verbose,
                    retain=True,
                )

    def start_passive_listeners(self):
        subscribe_and_callback(self.set_attr, f"morbidostat/{self.unit}/{self.experiment}/{self.job_name}/+/set")
