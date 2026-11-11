# -*- coding: utf-8 -*-
from __future__ import annotations

import click
import pytest
from pioreactor.calibrations import session_flow
from pioreactor.calibrations.structured_session import CalibrationStepField


def test_step_id_from_rejects_invalid_steps() -> None:
    class InvalidStep(session_flow.SessionStep):
        step_id = ""

    with pytest.raises(ValueError, match="Invalid step identifier"):
        session_flow._step_id_from(InvalidStep())


def test_validate_field_bounds_uses_custom_max_error() -> None:
    fields = [
        CalibrationStepField(
            name="count",
            label="count",
            field_type="int",
            minimum=1,
            maximum=3,
            max_error_msg="Too many",
        )
    ]

    with pytest.raises(ValueError, match="Too many"):
        session_flow._validate_field_bounds(fields, {"count": 5})


def test_prompt_for_calibration_choice_field_preserves_prompt_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def prompt(label: str, **kwargs: object) -> str:
        calls.append({"label": label, **kwargs})
        return "B"

    monkeypatch.setattr(click, "prompt", prompt)

    field = CalibrationStepField(
        name="mode",
        label="Mode",
        field_type="choice",
        options=["A", "B"],
        default="A",
    )

    assert session_flow._prompt_for_calibration_field(field) == "B"
    assert len(calls) == 1
    choice = calls[0].pop("type")
    assert isinstance(choice, click.Choice)
    assert choice.choices == ("A", "B")
    assert calls == [
        {
            "label": session_flow.cli_helpers.green("Mode"),
            "default": "A",
            "show_default": True,
            "prompt_suffix": ":",
        }
    ]


@pytest.mark.parametrize("field_type", ["float", "int", "string"])
def test_prompt_for_calibration_text_fields_preserves_prompt_options(
    monkeypatch: pytest.MonkeyPatch,
    field_type: str,
) -> None:
    calls: list[dict[str, object]] = []

    def prompt(label: str, **kwargs: object) -> str:
        calls.append({"label": label, **kwargs})
        return "value"

    monkeypatch.setattr(click, "prompt", prompt)

    field = CalibrationStepField(
        name="value",
        label="Value",
        field_type=field_type,
        default="default",
    )

    assert session_flow._prompt_for_calibration_field(field) == "value"
    assert calls == [
        {
            "label": session_flow.cli_helpers.green("Value"),
            "type": str,
            "default": "default",
            "show_default": True,
            "prompt_suffix": ":",
        }
    ]


def test_prompt_for_calibration_float_list_field_preserves_default_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def prompt(label: str, **kwargs: object) -> str:
        calls.append({"label": label, **kwargs})
        return "1.0,2.5"

    monkeypatch.setattr(click, "prompt", prompt)

    field = CalibrationStepField(
        name="values",
        label="Values",
        field_type="float_list",
        default=[1.0, 2.5],
    )

    assert session_flow._prompt_for_calibration_field(field) == "1.0,2.5"
    assert calls == [
        {
            "label": session_flow.cli_helpers.green("Values"),
            "type": str,
            "default": "1.0,2.5",
            "show_default": True,
            "prompt_suffix": ":",
        }
    ]


def test_prompt_for_calibration_bool_field_uses_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def confirm(label: str, **kwargs: object) -> bool:
        calls.append({"label": label, **kwargs})
        return True

    monkeypatch.setattr(click, "confirm", confirm)

    field = CalibrationStepField(
        name="overwrite",
        label="Overwrite?",
        field_type="bool",
        default=False,
    )

    assert session_flow._prompt_for_calibration_field(field) is True
    assert calls == [
        {
            "label": session_flow.cli_helpers.green("Overwrite?"),
            "default": False,
            "prompt_suffix": ":",
        }
    ]


def test_cli_wait_step_checks_automatically_without_prompting(monkeypatch: pytest.MonkeyPatch) -> None:
    from pioreactor.calibrations.structured_session import CalibrationSession

    class WaitStep(session_flow.SessionStep):
        step_id = "waiting"

        def render(self, ctx: session_flow.SessionContext) -> session_flow.CalibrationStep:
            return session_flow.steps.wait("Waiting", "Checking readiness", poll_interval_s=2)

        def advance(self, ctx: session_flow.SessionContext) -> None:
            ctx.data["checks"] = ctx.data.get("checks", 0) + 1
            if ctx.data["checks"] == 3:
                ctx.complete({"title": "Ready"})

    session = CalibrationSession(
        session_id="wait-test",
        protocol_name="test",
        target_device="test",
        status="in_progress",
        step_id="waiting",
        data={},
        created_at="",
        updated_at="",
    )
    sleeps: list[float] = []
    monkeypatch.setattr(session_flow.time, "sleep", sleeps.append)
    monkeypatch.setattr(click, "prompt", lambda *args, **kwargs: pytest.fail("Unexpected prompt"))
    session_flow.run_session_in_cli({"waiting": WaitStep}, session)
    assert session.status == "complete"
    assert sleeps == [2, 2, 2]


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf")])
def test_wait_interval_must_be_positive_and_finite(interval: float) -> None:
    with pytest.raises(ValueError, match="positive and finite"):
        session_flow.steps.wait("Waiting", "", interval)
