# -*- coding: utf-8 -*-
import json
import signal
import urllib.request
from pioreactor.background_jobs.base import BackgroundJob
from pioreactor.whoami import get_unit_name, UNIVERSAL_EXPERIMENT


SLACK_WEBHOOK = ""


class Logs2slack(BackgroundJob):
    def __init__(self, unit, experiment):
        super(Logs2slack, self).__init__(
            unit=unit, experiment=experiment, job_name="logs2slack"
        )
        self.start_passive_listeners()

    def publish_to_slack(self, msg):
        payload = json.loads(msg.payload)
        slack_msg = f"[{payload['level']}] [{payload['task']}] {payload['message']}"
        encoded_json = json.dumps({"text": slack_msg}).encode("utf-8")

        req = urllib.request.Request(SLACK_WEBHOOK)

        req.add_header("Content-Type", "application/json")
        req.add_header("Content-Length", len(encoded_json))

        urllib.request.urlopen(req, encoded_json)

    def start_passive_listeners(self):
        self.subscribe_and_callback(self.publish_to_slack, "pioreactor/+/+/logs/+")


if __name__ == "__main__":

    Logs2slack(unit=get_unit_name(), experiment=UNIVERSAL_EXPERIMENT)
    signal.pause()
