# -*- coding: utf-8 -*-
# utils.py
import typing as t
from pathlib import Path
from time import time
from typing import NewType
from typing import NoReturn

from flask import abort
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from flask.typing import ResponseReturnValue
from huey.exceptions import HueyException
from huey.exceptions import TaskException
from msgspec import DecodeError
from msgspec import Struct
from msgspec import to_builtins
from msgspec import ValidationError
from msgspec.structs import fields as struct_fields
from msgspec.yaml import decode as yaml_decode
from pioreactor import structs
from pioreactor.bioreactor import get_bioreactor_variable_definitions
from pioreactor.bioreactor import get_default_bioreactor_value
from pioreactor.experiment_profiles.diagnostics import Diagnostic
from pioreactor.http_response import UnitApiErrorPayload
from pioreactor.utils import local_intermittent_storage
from pioreactor.utils.files import is_valid_unix_filename  # noqa: F401 - re-export
from pioreactor.whoami import get_unit_name


RequestBody = t.TypeVar("RequestBody", bound=Struct)


def abort_with(
    status: int,
    description: str,
    *,
    remediation: str | None = None,
    cause: str | None = None,
    diagnostics: list[Diagnostic] | None = None,
) -> NoReturn:
    payload = UnitApiErrorPayload(
        error=description,
        status=status,
        cause=cause,
        remediation=remediation,
        diagnostics=diagnostics,
    )
    abort_with_payload(payload)


def abort_with_payload(payload: UnitApiErrorPayload) -> NoReturn:
    response = jsonify(t.cast(dict[str, t.Any], to_builtins(payload)))
    response.status_code = payload.status
    abort(response)
    raise AssertionError("abort should not return")


def decode_request_body(payload_type: type[RequestBody]) -> RequestBody:
    try:
        return current_app.json.loads(request.data, type=payload_type)
    except (DecodeError, ValidationError) as exc:
        required_fields = ", ".join(field.name for field in struct_fields(payload_type) if field.required)
        remediation = (
            f"Send a JSON object with the required fields: {required_fields}."
            if required_fields
            else "Send a valid JSON object."
        )
        abort_with(
            400,
            "Invalid request body.",
            cause=str(exc),
            remediation=remediation,
        )


def ensure_error_info(payload: dict[str, t.Any], status: int) -> UnitApiErrorPayload:
    message = _extract_error_message(payload)
    cause = payload.get("cause")
    normalized_cause = cause.strip() if isinstance(cause, str) and cause.strip() else message
    remediation = payload.get("remediation")
    normalized_remediation = (
        remediation.strip() if isinstance(remediation, str) and remediation.strip() else None
    )
    diagnostics = payload.get("diagnostics")
    normalized_diagnostics = diagnostics if isinstance(diagnostics, list) else None

    normalized_payload = UnitApiErrorPayload(
        status=status,
        error=message,
        cause=normalized_cause,
        remediation=normalized_remediation,
        diagnostics=normalized_diagnostics,
    )

    return normalized_payload


def _extract_error_message(payload: dict[str, t.Any]) -> str:
    value = payload.get("error")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "Request failed."


def attach_cache_control(response: Response, max_age: int = 5) -> Response:
    """
    Takes in a Flask Response object and sets the Cache-Control header
    to 'public, max-age=<max_age>'.
    """
    response.headers["Cache-Control"] = f"public, max-age={max_age}"
    return response


def wait_for_bool_task_result(task: t.Any, *, timeout_s: float = 10.0) -> bool:
    try:
        if hasattr(task, "get"):
            return bool(task.get(blocking=True, timeout=timeout_s))
        return bool(task)
    except (HueyException, TaskException):
        return False


DelayedResponseReturnValue = NewType("DelayedResponseReturnValue", ResponseReturnValue)  # type: ignore


def create_task_response(task: t.Any) -> DelayedResponseReturnValue:
    task_id = getattr(task, "id", None)
    if task_id is None:
        callback = getattr(task, "callback", None)
        task_id = getattr(callback, "id", None)

    if task_id is None:
        raise AttributeError("Task response object does not expose an id.")

    return (  # type: ignore
        jsonify(
            {
                "unit": get_unit_name(),
                "task_id": task_id,
                "result_url_path": f"/unit_api/task_results/{task_id}",
                "status": "accepted",
            }
        ),
        202,
    )


def validate_sqlite_identifier(value: str) -> str:
    """Return an unchanged identifier that is safe to interpolate into SQLite SQL."""
    if not value.isascii() or not value.isidentifier():
        raise ValueError(
            f"Invalid SQLite identifier {value!r}: use only ASCII letters, digits, and underscores, "
            "starting with a letter or underscore."
        )
    if value.lower().startswith("sqlite_"):
        raise ValueError(f"Invalid SQLite identifier {value!r}: names beginning with 'sqlite_' are reserved.")
    return value


def is_rate_limited(job: str, expire_time_seconds: float = 1.0) -> bool:
    """
    Check if the user has made a request within the debounce duration.
    """
    with local_intermittent_storage("debounce") as cache:
        now = time()
        if cache.set_if_absent(job, now):
            return False

        last_request_time = cache.getfloat(job)
        if (now - last_request_time) < expire_time_seconds:
            return True

        cache.set(job, now)
        return False


def validate_published_settings_descriptors(
    settings: list[structs.PublishedSettingsDescriptor],
) -> None:
    """
    UI settings descriptors must be semantically renderable, not just parseable.
    """
    seen_keys: set[str] = set()
    for setting in settings:
        if setting.key in seen_keys:
            raise ValueError(f"Duplicate published setting key: {setting.key}")
        seen_keys.add(setting.key)

        if setting.min is not None and setting.max is not None and setting.min > setting.max:
            raise ValueError(f"Published setting {setting.key} has min greater than max.")

        if setting.display and not setting.label:
            raise ValueError(f"Displayed published setting {setting.key} requires a label.")


def validate_background_job_descriptor(descriptor: structs.BackgroundJobDescriptor) -> None:
    validate_published_settings_descriptors(descriptor.published_settings)


def validate_settings_collection_descriptor(descriptor: structs.SettingsCollectionDescriptor) -> None:
    validate_published_settings_descriptors(descriptor.published_settings)


def validate_automation_descriptor(descriptor: structs.AutomationDescriptor) -> None:
    seen_keys: set[str] = set()
    for field in descriptor.fields:
        if field.key in seen_keys:
            raise ValueError(f"Duplicate automation field key: {field.key}")
        seen_keys.add(field.key)

        if field.type == "select" and not field.options:
            raise ValueError(f"Select automation field {field.key} requires options.")


def load_background_job_descriptors(
    dot_pioreactor_path: Path,
    *,
    report_error: t.Callable[[str], None] | None = None,
) -> list[structs.BackgroundJobDescriptor]:
    job_path_builtins = dot_pioreactor_path / "ui" / "jobs"
    job_path_plugins = dot_pioreactor_path / "plugins" / "ui" / "jobs"
    files = sorted(job_path_builtins.glob("*.y*ml")) + sorted(job_path_plugins.glob("*.y*ml"))

    parsed_yaml: dict[str, structs.BackgroundJobDescriptor] = {}

    for file in files:
        try:
            decoded_yaml = yaml_decode(file.read_bytes(), type=structs.BackgroundJobDescriptor)
            validate_background_job_descriptor(decoded_yaml)
            if decoded_yaml.job_name in parsed_yaml and report_error is not None:
                report_error(f"Descriptor {file.name} overrides job {decoded_yaml.job_name}.")
            parsed_yaml[decoded_yaml.job_name] = decoded_yaml
        except (ValidationError, DecodeError, ValueError) as e:
            if report_error is not None:
                report_error(f"Yaml error in {file.name}: {e}")

    return list(parsed_yaml.values())


def load_settings_collection_descriptors(
    dot_pioreactor_path: Path,
    *,
    report_error: t.Callable[[str], None] | None = None,
) -> list[structs.SettingsCollectionDescriptor]:
    settings_path_builtins = dot_pioreactor_path / "ui" / "settings"
    settings_path_plugins = dot_pioreactor_path / "plugins" / "ui" / "settings"
    files = sorted(settings_path_builtins.glob("*.y*ml")) + sorted(settings_path_plugins.glob("*.y*ml"))

    parsed_yaml: dict[str, structs.SettingsCollectionDescriptor] = {}
    bioreactor_variables = get_bioreactor_variable_definitions()

    for file in files:
        try:
            descriptor = yaml_decode(file.read_bytes(), type=structs.SettingsCollectionDescriptor)
            validate_settings_collection_descriptor(descriptor)
        except (ValidationError, DecodeError, ValueError) as e:
            if report_error is not None:
                report_error(f"Yaml error in {file.name}: {e}")
            continue

        if descriptor.key == "bioreactor":
            # bioreactor.yaml presents canonical bioreactor variables; it does not define new ones.
            descriptor.published_settings = [
                structs.PublishedSettingsDescriptor(
                    key=field.key,
                    type=field.type,
                    display=field.display,
                    description=field.description,
                    default=get_default_bioreactor_value(
                        field.key,
                        validate_against_model_capacity=False,
                    ),
                    unit=field.unit,
                    label=field.label,
                    editable=field.editable,
                    min=metadata.minimum,
                    max=metadata.maximum,
                )
                for field in descriptor.published_settings
                if (metadata := bioreactor_variables.get(field.key)) is not None
            ]

        if descriptor.key in parsed_yaml and report_error is not None:
            report_error(f"Descriptor {file.name} overrides settings collection {descriptor.key}.")
        parsed_yaml[descriptor.key] = descriptor

    return list(parsed_yaml.values())


def load_automation_descriptors(
    dot_pioreactor_path: Path,
    automation_type: str,
    *,
    report_error: t.Callable[[str], None] | None = None,
) -> list[structs.AutomationDescriptor]:
    automation_path_builtins = dot_pioreactor_path / "ui" / "automations" / automation_type
    automation_path_plugins = dot_pioreactor_path / "plugins" / "ui" / "automations" / automation_type
    files = sorted(automation_path_builtins.glob("*.y*ml")) + sorted(automation_path_plugins.glob("*.y*ml"))

    parsed_yaml: dict[str, structs.AutomationDescriptor] = {}

    for file in files:
        try:
            decoded_yaml = yaml_decode(file.read_bytes(), type=structs.AutomationDescriptor)
            validate_automation_descriptor(decoded_yaml)
            if decoded_yaml.automation_name in parsed_yaml and report_error is not None:
                report_error(f"Descriptor {file.name} overrides automation {decoded_yaml.automation_name}.")
            parsed_yaml[decoded_yaml.automation_name] = decoded_yaml
        except (ValidationError, DecodeError, ValueError) as e:
            if report_error is not None:
                report_error(f"Yaml error in {file.name}: {e}")

    return list(parsed_yaml.values())
