# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Literal

import click
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import CalibrationStepField
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp

SessionMode = Literal["ui", "cli"]
StepFlow = Callable[["SessionContext"], CalibrationStep]


@dataclass
class SessionInputs:
    raw: dict[str, object] | None

    @property
    def has_inputs(self) -> bool:
        return self.raw is not None

    def _get_raw(self, name: str) -> object | None:
        if self.raw is None:
            return None
        return self.raw.get(name)

    def str(self, name: str, default: str | None = None, required: bool = True) -> str:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is not None:
                return default
            if required:
                raise ValueError(f"Missing '{name}'.")
            return ""
        if not isinstance(value, str):
            raise ValueError(f"Invalid '{name}', expected string.")
        return value.strip()

    def float(
        self,
        name: str,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is None:
                raise ValueError(f"Missing '{name}'.")
            return float(default)
        if isinstance(value, (int, float)):
            numeric = float(value)
        elif isinstance(value, str):
            try:
                numeric = float(value.strip())
            except ValueError as exc:
                raise ValueError(f"Invalid '{name}', expected number.") from exc
        else:
            raise ValueError(f"Invalid '{name}', expected number.")
        if minimum is not None and numeric < minimum:
            raise ValueError(f"'{name}' must be >= {minimum}.")
        if maximum is not None and numeric > maximum:
            raise ValueError(f"'{name}' must be <= {maximum}.")
        return numeric

    def int(
        self,
        name: str,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is None:
                raise ValueError(f"Missing '{name}'.")
            return int(default)
        if isinstance(value, int):
            numeric = value
        elif isinstance(value, float):
            numeric = int(value)
        elif isinstance(value, str):
            try:
                numeric = int(value.strip())
            except ValueError as exc:
                raise ValueError(f"Invalid '{name}', expected integer.") from exc
        else:
            raise ValueError(f"Invalid '{name}', expected integer.")
        if minimum is not None and numeric < minimum:
            raise ValueError(f"'{name}' must be >= {minimum}.")
        if maximum is not None and numeric > maximum:
            raise ValueError(f"'{name}' must be <= {maximum}.")
        return numeric

    def choice(self, name: str, options: Iterable[str], default: str | None = None) -> str:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is None:
                raise ValueError(f"Missing '{name}'.")
            return default
        if not isinstance(value, str):
            raise ValueError(f"Invalid '{name}', expected string.")
        value = value.strip()
        if value not in options:
            raise ValueError(f"Invalid '{name}', expected one of {list(options)}.")
        return value

    def float_list(self, name: str, default: list[float] | None = None) -> list[float]:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is None:
                raise ValueError(f"Missing '{name}'.")
            return default
        if isinstance(value, list):
            if not value:
                raise ValueError(f"'{name}' cannot be empty.")
            return [float(item) for item in value]
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if not parts:
                raise ValueError(f"'{name}' cannot be empty.")
            return [float(part) for part in parts]
        raise ValueError(f"Invalid '{name}', expected list of numbers.")


@dataclass
class SessionContext:
    session: CalibrationSession
    mode: SessionMode
    inputs: SessionInputs
    collected_calibrations: list[Any]

    @property
    def step(self) -> str:
        return self.session.step_id

    @step.setter
    def step(self, value: str) -> None:
        self.session.step_id = value

    @property
    def data(self) -> dict[str, Any]:
        return self.session.data

    def ensure(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def abort(self, message: str) -> None:
        self.session.status = "aborted"
        self.session.error = message

    def complete(self, result: dict[str, Any]) -> None:
        self.session.status = "complete"
        self.session.result = result
        self.session.step_id = "complete"

    def store_calibration(self, calibration, device: str) -> dict[str, str | None]:
        self.collected_calibrations.append(calibration)
        if self.mode == "ui":
            path = calibration.save_to_disk_for_device(device)
        else:
            path = None
        return {"device": device, "calibration_name": calibration.calibration_name, "path": path}


class SessionEngine:
    def __init__(self, flow: StepFlow, session: CalibrationSession, mode: SessionMode) -> None:
        self.flow = flow
        self.ctx = SessionContext(
            session=session, mode=mode, inputs=SessionInputs(None), collected_calibrations=[]
        )

    @property
    def session(self) -> CalibrationSession:
        return self.ctx.session

    def get_step(self) -> CalibrationStep:
        self.ctx.inputs = SessionInputs(None)
        step = self.flow(self.ctx)
        if not step.step_id:
            step.step_id = self.session.step_id
        return step

    def advance(self, inputs: dict[str, object]) -> CalibrationStep:
        self.ctx.inputs = SessionInputs(inputs)
        self.session.updated_at = utc_iso_timestamp()
        self.flow(self.ctx)
        self.ctx.inputs = SessionInputs(None)
        step = self.flow(self.ctx)
        if not step.step_id:
            step.step_id = self.session.step_id
        return step

    def save(self) -> None:
        save_calibration_session(self.session)


class FieldBuilder:
    def str(self, name: str, label: str | None = None, default: str | None = None) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="string",
            default=default,
        )

    def float(
        self,
        name: str,
        label: str | None = None,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="float",
            minimum=minimum,
            maximum=maximum,
            default=default,
        )

    def int(
        self,
        name: str,
        label: str | None = None,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="int",
            minimum=minimum,
            maximum=maximum,
            default=default,
        )

    def choice(
        self,
        name: str,
        options: list[str],
        label: str | None = None,
        default: str | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="choice",
            options=options,
            default=default,
        )

    def float_list(
        self, name: str, label: str | None = None, default: list[float] | None = None
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="float_list",
            default=default,
        )


class StepBuilder:
    def info(self, title: str, body: str) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="info", title=title, body=body)

    def form(self, title: str, body: str, fields: list[CalibrationStepField]) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="form", title=title, body=body, fields=fields)

    def action(self, title: str, body: str) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="action", title=title, body=body)

    def result(self, result: dict[str, Any]) -> CalibrationStep:
        return CalibrationStep(
            step_id="complete",
            step_type="result",
            title="Calibration complete",
            body="Calibration results are ready.",
            metadata={"result": result},
        )


fields = FieldBuilder()
steps = StepBuilder()


def run_session_in_cli(flow: StepFlow, session: CalibrationSession) -> list[Any]:
    engine = SessionEngine(flow=flow, session=session, mode="cli")
    while engine.session.status == "in_progress":
        step = engine.get_step()
        if step.title:
            click.echo(step.title)
        if step.body:
            click.echo(step.body)
        click.echo()

        inputs: dict[str, object] = {}
        if step.fields:
            for field in step.fields:
                if field.field_type == "choice":
                    value = click.prompt(
                        field.label,
                        type=click.Choice(field.options or []),
                        default=field.default,
                        show_default=field.default is not None,
                    )
                elif field.field_type == "float":
                    value = click.prompt(
                        field.label,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                    )
                elif field.field_type == "int":
                    value = click.prompt(
                        field.label,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                    )
                elif field.field_type == "float_list":
                    value = click.prompt(
                        field.label,
                        type=str,
                        default=",".join(str(v) for v in (field.default or [])),
                        show_default=field.default is not None,
                    )
                elif field.field_type == "bool":
                    value = click.confirm(field.label, default=bool(field.default))
                else:
                    value = click.prompt(
                        field.label,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                    )
                inputs[field.name] = value
        else:
            click.prompt("Press enter to continue", default="", show_default=False, prompt_suffix="")
        engine.advance(inputs)

    return engine.ctx.collected_calibrations
