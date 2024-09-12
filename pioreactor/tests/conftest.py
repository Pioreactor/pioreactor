# -*- coding: utf-8 -*-
from __future__ import annotations

import contextlib
import re
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from pioreactor.mureq import Response


@pytest.fixture(autouse=True)
def run_around_tests(request):
    from pioreactor.utils import local_intermittent_storage
    from pioreactor.utils import local_persistant_storage

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

    with local_persistant_storage("current_od_calibration") as cache:
        for key in cache.iterkeys():
            del cache[key]

    with local_persistant_storage("media_throughput") as c:
        c.pop(test_name)
    with local_persistant_storage("alt_media_throughput") as c:
        c.pop(test_name)
    with local_persistant_storage("alt_media_fraction") as c:
        c.pop(test_name)
    with local_persistant_storage("vial_volume") as c:
        c.pop(test_name)

    yield


@pytest.fixture()
def active_workers_in_cluster():
    return ["unit1", "unit2"]


@pytest.fixture(autouse=True)
def mock_external_leader_webserver_apis(mocker, active_workers_in_cluster):
    # used mostly in pioreactor.config.py
    def mock_get_response(endpoint):
        if endpoint.endswith("/api/workers"):
            mm = MagicMock()
            mm.json.return_value = [
                {"pioreactor_unit": unit, "is_active": 1} for unit in active_workers_in_cluster
            ] + [{"pioreactor_unit": "notactiveworker", "is_active": 0}]
            return mm
        elif re.search("/api/experiments/.*/workers", endpoint):
            mm = MagicMock()
            mm.json.return_value = [
                {"pioreactor_unit": unit, "is_active": 1} for unit in active_workers_in_cluster
            ]
            return mm
        elif re.search("/api/workers/.*/experiment", endpoint):
            mm = MagicMock()
            mm.json.return_value = {"experiment": "_testing_experiment"}
            return mm
        else:
            raise ValueError(f"{endpoint} not mocked")

    mock_get = mocker.patch(
        "pioreactor.cluster_management.get_from_leader", autospec=True, side_effect=mock_get_response
    )

    return mock_get


class CapturedRequest:
    def __init__(self, method, url, headers, body):
        self.method = method
        self.url = url
        self.headers = headers
        self.body = body


@contextlib.contextmanager
def capture_requests():
    bucket = []

    def mock_request(method, url, **kwargs):
        # Capture the request details
        headers = kwargs.get("headers")
        body = kwargs.get("body", None)
        bucket.append(CapturedRequest(method, url, headers, body))

        # Return a mock response object
        return Response(url, 200, {}, b'{"mocked": "response"}')

    # Patch the mureq.request method
    with patch("pioreactor.mureq.request", side_effect=mock_request):
        yield bucket
