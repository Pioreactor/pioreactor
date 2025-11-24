# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import re
from unittest.mock import MagicMock
from unittest.mock import patch
from urllib.parse import urlparse

import pytest
from pioreactor.mureq import Response
from pioreactor.pubsub import prune_retained_messages
from pioreactor.pubsub import publish
from pioreactor.structs import ODReadings
from pioreactor.structs import RawODReading
from pioreactor.utils.timing import to_datetime


@pytest.fixture(autouse=True)
def run_around_tests(request):

    from pioreactor.utils import JobManager
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistent_storage

    yield

    # clean up any artifacts.
    test_name = request.node.name

    with local_intermittent_storage("pwm_dc") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_intermittent_storage("led_locks") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_intermittent_storage("pwm_locks") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_intermittent_storage("leds") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_persistent_storage("active_calibrations") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_persistent_storage("media_throughput") as c:
        c.pop(test_name)
    with local_persistent_storage("alt_media_throughput") as c:
        c.pop(test_name)
    with local_persistent_storage("alt_media_fraction") as c:
        c.pop(test_name)
    with local_persistent_storage("current_volume_ml") as c:
        c.pop(test_name)

    prune_retained_messages("pioreactor/#")

    with JobManager() as job_manager:
        job_manager.clear()


@pytest.fixture()
def active_workers_in_cluster():
    return ["unit1", "unit2"]


@pytest.fixture(autouse=True)
def mock_external_leader_webserver_apis(mocker, active_workers_in_cluster):
    def mock_get_response(endpoint):
        mm = MagicMock()
        if endpoint.endswith("/api/workers"):
            mm.json.return_value = [
                {"pioreactor_unit": unit, "is_active": 1} for unit in active_workers_in_cluster
            ] + [{"pioreactor_unit": "notactiveworker", "is_active": 0}]
            return mm
        elif re.search("/api/experiments/.*/workers", endpoint):
            mm.json.return_value = [
                {"pioreactor_unit": unit, "is_active": 1} for unit in active_workers_in_cluster
            ]
            return mm
        elif re.search("/api/workers/.*/experiment", endpoint):
            mm.json.return_value = {"experiment": "_testing_experiment"}
            return mm
        else:
            raise ValueError(f"TODO: {endpoint} not mocked")

    mock_get = mocker.patch(
        "pioreactor.cluster_management.get_from_leader", autospec=True, side_effect=mock_get_response
    )

    return mock_get


class CapturedRequest:
    def __init__(self, method, url, headers, body, json, params) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body
        self.json = json
        self.params = params

        r = urlparse(url)

        self.path = r.path

    def __lt__(self, other):
        return self.path < other.path


@contextlib.contextmanager
def capture_requests():
    bucket = []

    def mock_request(method, url, **kwargs):
        # Capture the request details
        headers = kwargs.get("headers")
        body = kwargs.get("body", None)
        json = kwargs.get("json", None)
        params = kwargs.get("params", None)
        bucket.append(CapturedRequest(method, url, headers, body, json, params))
        if re.search("/api/workers/.*/jobs/update/job_name/.*/experiments/.*", url):
            # fire a mqtt too
            r = re.search("/api/workers/(.*)/jobs/update/job_name/(.*)/experiments/(.*)", url)
            for setting, v in json["settings"].items():
                publish(f"pioreactor/{r.groups()[0]}/{r.groups()[2]}/{r.groups()[1]}/{setting}/set", v)

        # Return a mock response object
        return Response(url, 200, {}, b'{"mocked": "response"}')

    # Patch the mureq.request method
    with patch("pioreactor.mureq.request", side_effect=mock_request):
        yield bucket


class StreamODReadingsFromExport:
    def __init__(self, filename: str, skip_first_n_rows=0) -> None:
        self.filename = filename
        self.skip_first_n_rows = skip_first_n_rows

    def __enter__(self, *args, **kwargs):
        import csv

        self.file_instance = open(self.filename, "r")
        self.csv_reader = csv.DictReader(self.file_instance, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, *args, **kwargs):
        self.file_instance.close()

    def __iter__(self):
        for i, line in enumerate(self.csv_reader):
            if i <= self.skip_first_n_rows:
                continue
            dt = to_datetime(line["timestamp"])
            od = RawODReading(
                angle=line["angle"], channel=line["channel"], timestamp=dt, od=float(line["od_reading"])
            )
            ods = ODReadings(timestamp=dt, ods={"2": od})
            yield ods
