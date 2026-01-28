# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any
from typing import Callable
from typing import Iterable
from typing import Literal

import click
from msgspec import to_builtins
from pioreactor.calibrations import cli_helpers
from pioreactor.calibrations.structured_session import CalibrationSession
from pioreactor.calibrations.structured_session import CalibrationStep
from pioreactor.calibrations.structured_session import CalibrationStepField
from pioreactor.calibrations.structured_session import save_calibration_session
from pioreactor.calibrations.structured_session import utc_iso_timestamp
from pioreactor.calibrations.utils import plot_data

SessionMode = Literal["ui", "cli"]
Str = str
Float = float
SessionExecutor = Callable[[Str, dict[Str, object]], dict[Str, object]]


class SessionStep:
    step_id = ""

    def render(self, ctx: "SessionContext") -> CalibrationStep:
        raise NotImplementedError("Step must implement render().")

    def advance(self, ctx: "SessionContext") -> "StepLike | None":
        return None


StepLike = str | SessionStep | type[SessionStep]
# Registry of step_id -> SessionStep class for a protocol's session flow.
StepRegistry = dict[Str, type[SessionStep]]


def _step_id_from(step: StepLike) -> Str:
    if isinstance(step, str):
        return step
    step_id = getattr(step, "step_id", None)
    if not isinstance(step_id, str) or not step_id:
        raise ValueError("Invalid step identifier.")
    return step_id


def resolve_step(registry: StepRegistry, step_id: Str) -> SessionStep:
    step_class = registry.get(step_id)
    if step_class is None:
        raise KeyError(f"Unknown step: {step_id}")
    return step_class()


def with_terminal_steps(step_registry: StepRegistry) -> StepRegistry:
    return {
        CalibrationComplete.step_id: CalibrationComplete,
        CalibrationEnded.step_id: CalibrationEnded,
        **step_registry,
    }


class SessionInputs:
    def __init__(self, raw: dict[Str, object] | None) -> None:
        self.raw = raw

    @property
    def has_inputs(self) -> bool:
        return self.raw is not None

    def _get_raw(self, name: Str) -> object | None:
        if self.raw is None:
            return None
        return self.raw.get(name)

    def str(self, name: Str, default: Str | None = None, required: bool = True) -> Str:
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
        name: Str,
        minimum: Float | None = None,
        maximum: Float | None = None,
        default: Float | None = None,
    ) -> Float:
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
        name: Str,
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

    def bool(self, name: Str, default: bool | None = None) -> bool:
        value = self._get_raw(name)
        if value is None or value == "":
            if default is None:
                raise ValueError(f"Missing '{name}'.")
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "y"}:
                return True
            if normalized in {"false", "no", "0", "n"}:
                return False
        raise ValueError(f"Invalid '{name}', expected boolean.")

    def choice(self, name: Str, options: Iterable[Str], default: Str | None = None) -> Str:
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

    def float_list(self, name: Str, default: list[Float] | None = None) -> list[Float]:
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


class SessionContext:
    def __init__(
        self,
        session: CalibrationSession,
        mode: SessionMode,
        inputs: SessionInputs,
        collected_calibrations: list[Any],
        executor: SessionExecutor | None = None,
    ) -> None:
        self.session = session
        self.mode = mode
        self.inputs = inputs
        self.collected_calibrations = collected_calibrations
        self.executor = executor

    @property
    def step(self) -> Str:
        return self.session.step_id

    @step.setter
    def step(self, value: StepLike) -> None:
        self.session.step_id = _step_id_from(value)

    @property
    def data(self) -> dict[Str, Any]:
        return self.session.data

    def complete(self, result: dict[Str, Any]) -> None:
        self.session.status = "complete"
        self.session.result = result
        self.session.step_id = "complete"

    def store_calibration(
        self,
        calibration,
        device: Str,
    ) -> dict[Str, str | None]:
        self.collected_calibrations.append(calibration)
        if self.mode == "ui":
            assert self.executor is not None
            payload = self.executor(
                "save_calibration",
                {"device": device, "calibration": to_builtins(calibration)},
            )
            path = payload.get("path")
        else:
            path = None
        return {"device": device, "calibration_name": calibration.calibration_name, "path": path}

    def store_estimator(
        self,
        estimator,
        device: Str,
    ) -> dict[Str, str | None]:
        self.collected_calibrations.append(estimator)
        if self.mode == "ui":
            if not self.executor:
                raise ValueError("Estimator saver is only available in UI sessions.")
            payload = self.executor(
                "save_estimator",
                {"device": device, "estimator": to_builtins(estimator)},
            )
            if not isinstance(payload, dict):
                raise ValueError("Invalid estimator save payload.")
            saved_path = payload.get("path")
            if not isinstance(saved_path, str):
                raise ValueError("Invalid estimator save payload.")
            path = saved_path
        else:
            path = None
        return {"device": device, "estimator_name": estimator.estimator_name, "path": path}

    def read_voltage(self) -> Float:
        if not self.executor or self.mode != "ui":
            raise ValueError("Voltage reader is only available in UI sessions.")
        payload = self.executor("read_aux_voltage", {})
        value = payload.get("voltage")
        if not isinstance(value, (int, float, str)):
            raise ValueError("Invalid voltage payload.")
        return float(value)

    def goto(self, step: StepLike) -> None:
        self.step = step


class SessionEngine:
    def __init__(
        self,
        step_registry: StepRegistry,
        session: CalibrationSession,
        mode: SessionMode,
        executor: SessionExecutor | None = None,
    ) -> None:
        self.step_registry = step_registry
        self.ctx = SessionContext(
            session=session,
            mode=mode,
            inputs=SessionInputs(None),
            collected_calibrations=[],
            executor=executor,
        )

    @property
    def session(self) -> CalibrationSession:
        return self.ctx.session

    def _render_terminal_step(self) -> CalibrationStep:
        if self.session.step_id == "complete":
            step_handler = resolve_step(self.step_registry, "complete")
            step = step_handler.render(self.ctx)
            if not step.step_id:
                step.step_id = self.session.step_id
            return step
        if self.session.step_id == "ended" and "ended" in self.step_registry:
            step_handler = resolve_step(self.step_registry, "ended")
            step = step_handler.render(self.ctx)
            if not step.step_id:
                step.step_id = self.session.step_id
            return step
        if self.session.result is not None:
            return steps.result(self.session.result)
        return steps.info("Protocol ended", "This protocol session has ended.")

    def _render_current_step(self) -> CalibrationStep:
        step_handler = resolve_step(self.step_registry, self.session.step_id)
        step = step_handler.render(self.ctx)
        if not step.step_id:
            step.step_id = self.session.step_id
        return step

    def get_step(self) -> CalibrationStep:
        self.ctx.inputs = SessionInputs(None)
        if self.session.status != "in_progress":
            return self._render_terminal_step()
        return self._render_current_step()

    def advance(self, inputs: dict[Str, object]) -> CalibrationStep:
        self.ctx.inputs = SessionInputs(inputs)
        self.session.updated_at = utc_iso_timestamp()
        if self.session.status == "in_progress":
            step_handler = resolve_step(self.step_registry, self.session.step_id)
            next_step = step_handler.advance(self.ctx)
            if next_step is not None:
                self.ctx.goto(next_step)
        self.ctx.inputs = SessionInputs(None)
        if self.session.status != "in_progress":
            return self._render_terminal_step()
        return self._render_current_step()

    def save(self) -> None:
        save_calibration_session(self.session)


class FieldBuilder:
    def str(
        self,
        name: Str,
        label: Str | None = None,
        default: Str | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="string",
            default=default,
        )

    def float(
        self,
        name: Str,
        label: Str | None = None,
        minimum: Float | None = None,
        maximum: Float | None = None,
        default: Float | None = None,
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
        name: Str,
        label: Str | None = None,
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

    def bool(
        self,
        name: Str,
        label: Str | None = None,
        default: bool | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="bool",
            options=["yes", "no"],
            default=default,
        )

    def choice(
        self,
        name: Str,
        options: list[Str],
        label: Str | None = None,
        default: Str | None = None,
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="choice",
            options=options,
            default=default,
        )

    def float_list(
        self, name: Str, label: Str | None = None, default: list[Float] | None = None
    ) -> CalibrationStepField:
        return CalibrationStepField(
            name=name,
            label=label or name,
            field_type="float_list",
            default=default,
        )


class StepBuilder:
    def info(self, title: Str, body: Str) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="info", title=title, body=body)

    def form(self, title: Str, body: Str, fields: list[CalibrationStepField]) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="form", title=title, body=body, fields=fields)

    def action(self, title: Str, body: Str) -> CalibrationStep:
        return CalibrationStep(step_id="", step_type="action", title=title, body=body)

    def result(self, result: dict[Str, Any]) -> CalibrationStep:
        return CalibrationStep(
            step_id="complete",
            step_type="result",
            title=result.get("title", "Calibration complete!"),
            metadata={"result": result},
        )


fields = FieldBuilder()
steps = StepBuilder()


def _render_chart_for_cli(chart: dict[Str, Any]) -> None:
    title = chart.get("title", "")
    x_label = chart.get("x_label", "")
    y_label = chart.get("y_label", "")
    series: list = chart.get("series", [])

    multiple_series = len(series) > 1
    for entry in series:
        points = entry["points"]
        x_vals: list[float] = []
        y_vals: list[float] = []
        for point in points:
            x_vals.append(float(point["x"]))
            y_vals.append(float(point["y"]))
        if not x_vals or not y_vals:
            continue
        entry_title = str(title) if isinstance(title, str) else ""
        if multiple_series:
            label = entry.get("label", entry.get("id", "series"))
            entry_title = f"{entry_title} - {label}" if entry_title else str(label)
        plot_data(
            x_vals,
            y_vals,
            entry_title or "Calibration progress",
            str(x_label),
            str(y_label),
            interpolation_curve=None,
            highlight_recent_point=True,
        )


def render_step_for_cli(step: CalibrationStep) -> None:
    click.clear()
    if step.title:
        cli_helpers.info_heading(step.title)
    if step.body:
        if step.step_type == "action":
            cli_helpers.action_block(step.body.splitlines())
        else:
            cli_helpers.info(step.body)
    if step.metadata and isinstance(step.metadata, dict):
        chart = step.metadata.get("chart")
        if chart:
            _render_chart_for_cli(chart)
    click.echo()


def run_session_in_cli(step_registry: StepRegistry, session: CalibrationSession) -> list[Any]:
    engine = SessionEngine(step_registry=with_terminal_steps(step_registry), session=session, mode="cli")
    while engine.session.status == "in_progress":
        step = engine.get_step()
        render_step_for_cli(step)

        inputs: dict[Str, object] = {}
        if step.fields:
            for field in step.fields:
                prompt = cli_helpers.green(field.label)
                if field.field_type == "choice":
                    value = click.prompt(
                        prompt,
                        type=click.Choice(field.options or []),
                        default=field.default,
                        show_default=field.default is not None,
                        prompt_suffix=":",
                    )
                elif field.field_type == "float":
                    value = click.prompt(
                        prompt,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                        prompt_suffix=":",
                    )
                elif field.field_type == "int":
                    value = click.prompt(
                        prompt,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                        prompt_suffix=":",
                    )
                elif field.field_type == "float_list":
                    value = click.prompt(
                        prompt,
                        type=str,
                        default=",".join(str(v) for v in (field.default or [])),
                        show_default=field.default is not None,
                        prompt_suffix=":",
                    )
                elif field.field_type == "bool":
                    value = click.confirm(
                        prompt,
                        default=bool(field.default),
                        prompt_suffix=":",
                    )
                else:
                    value = click.prompt(
                        prompt,
                        type=str,
                        default=field.default,
                        show_default=field.default is not None,
                        prompt_suffix=":",
                    )
                inputs[field.name] = value
        else:
            click.prompt(
                cli_helpers.green("Press enter to continue..."),
                default="",
                show_default=False,
                prompt_suffix="",
            )
        engine.advance(inputs)

    return engine.ctx.collected_calibrations


class CalibrationComplete(SessionStep):
    step_id = "complete"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        return steps.result(ctx.session.result or {})


class CalibrationEnded(SessionStep):
    step_id = "ended"

    def render(self, ctx: SessionContext) -> CalibrationStep:
        status = ctx.session.status
        message = "This protocol session has ended."
        if status == "aborted":
            message = ctx.session.error or "This protocol session was aborted."
        elif status == "failed":
            message = ctx.session.error or "This protocol session failed."
        return steps.info("Protocol ended", message)


def get_session_step(
    step_registry: StepRegistry,
    session: CalibrationSession,
    executor: SessionExecutor | None = None,
) -> CalibrationStep:
    engine = SessionEngine(
        step_registry=with_terminal_steps(step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )
    return engine.get_step()


def advance_session(
    step_registry: StepRegistry,
    session: CalibrationSession,
    inputs: dict[Str, object],
    executor: SessionExecutor | None = None,
) -> CalibrationSession:
    engine = SessionEngine(
        step_registry=with_terminal_steps(step_registry),
        session=session,
        mode="ui",
        executor=executor,
    )
    engine.advance(inputs)
    return engine.session
