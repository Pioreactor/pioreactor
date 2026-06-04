# -*- coding: utf-8 -*-
import json
import subprocess
import sys

from pioreactor.http_response import summarize_error_response
from pioreactor.mureq import Response


def test_http_response_import_does_not_load_experiment_profile_runtime() -> None:
    command = (
        "import json, sys; "
        "import pioreactor.http_response; "
        "modules = ["
        "'pioreactor.experiment_profiles.validate', "
        "'pioreactor.experiment_profiles.parser', "
        "'pioreactor.pubsub', "
        "'paho.mqtt.client', "
        "'pioreactor.config'"
        "]; "
        "print(json.dumps({name: name in sys.modules for name in modules}))"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        capture_output=True,
        text=True,
    )

    imported_modules = json.loads(result.stdout)
    assert imported_modules == {
        "pioreactor.experiment_profiles.validate": False,
        "pioreactor.experiment_profiles.parser": False,
        "pioreactor.pubsub": False,
        "paho.mqtt.client": False,
        "pioreactor.config": False,
    }


def test_summarize_error_response_includes_structured_details() -> None:
    response = Response(
        "http://unit1.local/unit_api/system/reboot",
        400,
        {"Content-Type": "application/json"},
        (
            b'{"error":"Unable to reboot.","status":400,'
            b'"cause":"A job is still running.","remediation":"Stop the job and retry."}'
        ),
    )

    assert summarize_error_response(response) == (
        "HTTP 400: Unable to reboot. "
        "Cause: A job is still running. "
        "Remediation: Stop the job and retry."
    )


def test_summarize_error_response_rejects_mismatched_status() -> None:
    response = Response(
        "http://unit1.local/unit_api/system/reboot",
        500,
        {"Content-Type": "application/json"},
        b'{"error":"Unable to reboot.","status":400}',
    )

    assert summarize_error_response(response) == "HTTP 500."
