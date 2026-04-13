# -*- coding: utf-8 -*-
import re
from typing import Any
from typing import Literal

from msgspec import Struct
from pioreactor.experiment_profiles import profile_struct as struct
from pioreactor.experiment_profiles.parser import check_syntax


STRICT_EXPRESSION_PATTERN = r"^\${{(.*?)}}$"
FLEXIBLE_EXPRESSION_PATTERN = r"\${{(.*?)}}"


class Diagnostic(Struct, forbid_unknown_fields=True, omit_defaults=True):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    path: str
    hint: str | None = None


class ValidationResult(Struct, forbid_unknown_fields=True):
    ok: bool
    diagnostics: list[Diagnostic]
    normalized_profile: struct.Profile | None = None


def is_bracketed_expression(value: Any) -> bool:
    return isinstance(value, str) and bool(re.search(STRICT_EXPRESSION_PATTERN, value))


def strip_expression_brackets(value: str) -> str:
    match = re.search(STRICT_EXPRESSION_PATTERN, value)
    assert match is not None
    return match.group(1)


def check_syntax_of_bool_expression(bool_expression: str | bool) -> str | None:
    if isinstance(bool_expression, bool):
        return None

    if is_bracketed_expression(bool_expression):
        bool_expression = strip_expression_brackets(bool_expression)

    quoted_matches = re.findall(r'"[^"]*"|\'[^\']*\'', bool_expression)
    if quoted_matches:
        return (
            "Quoted string literals are not supported in profile expressions. " f"Found {quoted_matches[0]}."
        )

    bool_expression = bool_expression.replace("::", "dummy:", 1)

    if check_syntax(bool_expression):
        return None
    return "Syntax error in expression."


def time_to_seconds(value: float | int | str) -> float:
    if isinstance(value, (float, int)):
        return hours_to_seconds(value)

    if not isinstance(value, str):
        raise ValueError(f"Invalid time literal type: {type(value)}")

    s = value.strip().lower()
    match = re.fullmatch(r"([0-9]*\.?[0-9]+)([smhd])", s)
    if not match:
        raise ValueError(
            f"Invalid time literal '{value}'. "
            "Expected float hours or string like '10s', '15m', '1.5h', '2d'."
        )

    number = float(match.group(1))
    unit = match.group(2)

    if number < 0:
        raise ValueError(f"Time value cannot be negative: {value}")

    if unit == "s":
        return number
    if unit == "m":
        return number * 60.0
    if unit == "h":
        return number * 3600.0
    if unit == "d":
        return number * 86400.0

    raise ValueError(f"Unhandled time unit '{unit}' in literal '{value}'.")


def hours_to_seconds(hours: float) -> float:
    return hours * 60 * 60


def _iter_profile_actions(profile: struct.Profile) -> list[tuple[str, struct.Action]]:
    actions: list[tuple[str, struct.Action]] = []

    for job_name, job in profile.common.jobs.items():
        actions.extend(_iter_job_actions(job, f"common.jobs.{job_name}"))

    for unit_name, block in profile.pioreactors.items():
        for job_name, job in block.jobs.items():
            actions.extend(_iter_job_actions(job, f"pioreactors.{unit_name}.jobs.{job_name}"))

    return actions


def _iter_job_actions(job: struct.Job, job_path: str) -> list[tuple[str, struct.Action]]:
    actions: list[tuple[str, struct.Action]] = []

    for index, action in enumerate(job.actions):
        actions.extend(_iter_action(action, f"{job_path}.actions[{index}]"))

    return actions


def _iter_action(action: struct.Action, path: str) -> list[tuple[str, struct.Action]]:
    actions = [(path, action)]

    if isinstance(action, (struct.Repeat, struct.When)):
        for index, nested_action in enumerate(action.actions):
            actions.extend(_iter_action(nested_action, f"{path}.actions[{index}]"))

    return actions


def _append_error(
    diagnostics: list[Diagnostic], code: str, message: str, path: str, hint: str | None = None
) -> None:
    diagnostics.append(Diagnostic(severity="error", code=code, message=message, path=path, hint=hint))


def _append_warning(
    diagnostics: list[Diagnostic], code: str, message: str, path: str, hint: str | None = None
) -> None:
    diagnostics.append(Diagnostic(severity="warning", code=code, message=message, path=path, hint=hint))


def _validate_time_field(
    diagnostics: list[Diagnostic],
    *,
    path: str,
    field_name: str,
    value: float | int | str | None,
    must_be_positive: bool = False,
) -> float | None:
    if value is None:
        return None

    try:
        seconds = time_to_seconds(value)
    except ValueError as exc:
        _append_error(
            diagnostics,
            "time.invalid",
            str(exc),
            f"{path}.{field_name}",
        )
        return None

    if must_be_positive and seconds <= 0:
        _append_error(
            diagnostics,
            "time.non_positive",
            f"`{field_name}` must be greater than zero.",
            f"{path}.{field_name}",
        )
        return None

    if not must_be_positive and seconds < 0:
        _append_error(
            diagnostics,
            "time.negative",
            f"`{field_name}` cannot be negative.",
            f"{path}.{field_name}",
        )
        return None

    return seconds


def _validate_expression_field(
    diagnostics: list[Diagnostic], *, path: str, expression: str | bool, field_name: str | None = None
) -> None:
    error = check_syntax_of_bool_expression(expression)
    if error is None:
        return

    target_path = f"{path}.{field_name}" if field_name is not None else path
    _append_error(
        diagnostics,
        "expression.syntax",
        error,
        target_path,
    )


def _validate_options_expressions(
    diagnostics: list[Diagnostic], *, path: str, options: dict[str, Any]
) -> None:
    for key, value in options.items():
        if is_bracketed_expression(value):
            _validate_expression_field(
                diagnostics,
                path=f"{path}.options.{key}",
                expression=value,
            )


def _validate_log_message_expressions(diagnostics: list[Diagnostic], *, path: str, message: str) -> None:
    for match in re.findall(FLEXIBLE_EXPRESSION_PATTERN, message):
        _validate_expression_field(
            diagnostics,
            path=f"{path}.options.message",
            expression=match,
        )


def _validate_action_structure(diagnostics: list[Diagnostic], *, path: str, action: struct.Action) -> None:
    has_hours_elapsed = action.hours_elapsed is not None
    has_t = action.t is not None

    if has_hours_elapsed and has_t:
        _append_error(
            diagnostics,
            "action.time.conflict",
            "Action cannot define both `hours_elapsed` and `t`.",
            path,
            hint="Choose one time field per action.",
        )
    elif not has_hours_elapsed and not has_t:
        _append_error(
            diagnostics,
            "action.time.missing",
            "Action must define exactly one of `hours_elapsed` or `t`.",
            path,
        )

    if isinstance(action, struct.When):
        has_condition = bool(action.condition_)
        has_wait_until = bool(action.wait_until)
        if not has_condition and not has_wait_until:
            _append_error(
                diagnostics,
                "when.condition.missing",
                "`when` must define `condition` or `wait_until`.",
                path,
            )
        elif has_condition and has_wait_until:
            _append_warning(
                diagnostics,
                "when.condition.ambiguous",
                "`when` defines both `condition` and `wait_until`; `wait_until` will be used.",
                path,
            )

    if isinstance(action, struct.Repeat):
        has_repeat_every_hours = action.repeat_every_hours is not None
        has_every = action.every is not None
        if not has_repeat_every_hours and not has_every:
            _append_error(
                diagnostics,
                "repeat.every.missing",
                "`repeat` must define `repeat_every_hours` or `every`.",
                path,
            )
        elif has_repeat_every_hours and has_every:
            _append_warning(
                diagnostics,
                "repeat.every.ambiguous",
                "`repeat` defines both `repeat_every_hours` and `every`; `repeat_every_hours` will be used.",
                path,
            )


def _validate_action_time_semantics(
    diagnostics: list[Diagnostic], *, path: str, action: struct.Action
) -> None:
    if action.hours_elapsed is not None:
        _validate_time_field(
            diagnostics,
            path=path,
            field_name="hours_elapsed",
            value=action.hours_elapsed,
        )

    if action.t is not None:
        _validate_time_field(
            diagnostics,
            path=path,
            field_name="t",
            value=action.t,
        )

    if isinstance(action, struct.Repeat):
        repeat_seconds = _validate_time_field(
            diagnostics,
            path=path,
            field_name="repeat_every_hours" if action.repeat_every_hours is not None else "every",
            value=action.repeat_every_hours if action.repeat_every_hours is not None else action.every,
            must_be_positive=True,
        )

        if action.max_hours is not None:
            _validate_time_field(
                diagnostics,
                path=path,
                field_name="max_hours",
                value=action.max_hours,
                must_be_positive=True,
            )

        if action.max_time is not None:
            _validate_time_field(
                diagnostics,
                path=path,
                field_name="max_time",
                value=action.max_time,
                must_be_positive=True,
            )

        if repeat_seconds is not None:
            for index, nested_action in enumerate(action.actions):
                nested_path = f"{path}.actions[{index}]"
                field_name = "t" if nested_action.t is not None else "hours_elapsed"
                nested_value = nested_action.t if nested_action.t is not None else nested_action.hours_elapsed
                if nested_value is None:
                    continue

                nested_seconds = _validate_time_field(
                    diagnostics,
                    path=nested_path,
                    field_name=field_name,
                    value=nested_value,
                )
                if (nested_seconds is not None) and (nested_seconds > repeat_seconds):
                    _append_warning(
                        diagnostics,
                        "repeat.unreachable_action",
                        "Action start time exceeds repeat cycle and will never run.",
                        f"{nested_path}.{field_name}",
                        hint="Move the action earlier or increase the repeat interval.",
                    )


def _validate_action_expressions(diagnostics: list[Diagnostic], *, path: str, action: struct.Action) -> None:
    _validate_expression_field(diagnostics, path=path, expression=action.if_, field_name="if")

    if isinstance(action, struct.When):
        if action.condition_:
            _validate_expression_field(
                diagnostics,
                path=path,
                expression=action.condition_,
                field_name="condition",
            )
        if action.wait_until:
            _validate_expression_field(
                diagnostics,
                path=path,
                expression=action.wait_until,
                field_name="wait_until",
            )

    if isinstance(action, struct.Repeat):
        _validate_expression_field(
            diagnostics,
            path=path,
            expression=action.while_,
            field_name="while",
        )

    if isinstance(action, (struct.Start, struct.Update)):
        _validate_options_expressions(diagnostics, path=path, options=action.options)

    if isinstance(action, struct.Log):
        _validate_log_message_expressions(diagnostics, path=path, message=action.options.message)


def _validate_execution_order_for_job(
    diagnostics: list[Diagnostic], *, path: str, actions: list[struct.Action]
) -> None:
    has_started = False

    for index, action in enumerate(actions):
        action_path = f"{path}.actions[{index}]"

        if isinstance(action, struct.Start):
            has_started = True
        elif (
            isinstance(action, (struct.Stop, struct.Pause, struct.Resume, struct.Update)) and not has_started
        ):
            _append_warning(
                diagnostics,
                "job.ordering.before_start",
                f"`{action}` occurs before any `start` action for this job.",
                action_path,
            )
            if isinstance(action, struct.Stop):
                has_started = False
        elif isinstance(action, struct.Stop):
            has_started = False


def validate_profile(profile: struct.Profile) -> ValidationResult:
    diagnostics: list[Diagnostic] = []

    for path, action in _iter_profile_actions(profile):
        _validate_action_structure(diagnostics, path=path, action=action)
        _validate_action_time_semantics(diagnostics, path=path, action=action)
        _validate_action_expressions(diagnostics, path=path, action=action)

    for job_name, job in profile.common.jobs.items():
        _validate_execution_order_for_job(
            diagnostics,
            path=f"common.jobs.{job_name}",
            actions=job.actions,
        )

    for unit_name, block in profile.pioreactors.items():
        for job_name, job in block.jobs.items():
            _validate_execution_order_for_job(
                diagnostics,
                path=f"pioreactors.{unit_name}.jobs.{job_name}",
                actions=job.actions,
            )

    return ValidationResult(
        ok=not any(diagnostic.severity == "error" for diagnostic in diagnostics),
        diagnostics=diagnostics,
        normalized_profile=profile,
    )
