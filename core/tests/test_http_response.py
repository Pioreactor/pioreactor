# -*- coding: utf-8 -*-
from pioreactor.http_response import summarize_error_response
from pioreactor.mureq import Response


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
