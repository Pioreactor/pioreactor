# -*- coding: utf-8 -*-
from dataclasses import dataclass
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
from pioreactor.calibrations.utils import curve_to_callable
from pioreactor.calibrations.utils import plot_data

SessionMode = Literal["ui", "cli"]
SessionExecutor = Callable[[str, dict[str, object]], dict[str, object]]
Str = str
Float = float
Int = int


class SessionStep:
    step_id: str = ""

    def render(self, ctx: "SessionContext") -> CalibrationStep:
        raise NotImplementedError("Step must implement render().")

    def advance(self, ctx: "SessionContext") -> "StepLike | None":
        return None


StepLike = str | SessionStep | type[SessionStep]
# Registry of step_id -> SessionStep class for a protocol's session flow.
StepRegistry = dict[str, type[SessionStep]]


def _step_id_from(step: StepLike) -> str:
    if isinstance(step, str):
        return step
    step_id = getattr(step, "step_id", None)
    if not isinstance(step_id, str) or not step_id:
        raise ValueError("Invalid step identifier.")
    return step_id


def resolve_step(registry: StepRegistry, step_id: str) -> SessionStep:
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


@dataclass
class SessionInputs:
    raw: dict[str, object] | None

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
        minimum: Int | None = None,
        maximum: Int | None = None,
        default: Int | None = None,
    ) -> Int:
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


@dataclass
class SessionContext:
    session: CalibrationSession
    mode: SessionMode
    inputs: SessionInputs
    collected_calibrations: list[Any]
    executor: SessionExecutor | None = None

    @property
    def step(self) -> str:
        return self.session.step_id

    @step.setter
    def step(self, value: StepLike) -> None:
        self.session.step_id = _step_id_from(value)

    @property
    def data(self) -> dict[str, Any]:
        return self.session.data

    def ensure(self, condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(message)

    def abort(self, message: str) -> None:
        self.session.status = "aborted"
        self.session.error = message
        self.session.step_id = "ended"

    def fail(self, message: str) -> None:
        self.session.status = "failed"
        self.session.error = message
        self.session.step_id = "ended"

    def complete(self, result: dict[str, Any]) -> None:
        self.session.status = "complete"
        self.session.result = result
        self.session.step_id = "complete"

    def store_calibration(
        self,
        calibration,
        device: str,
    ) -> dict[str, str | None]:
        self.collected_calibrations.append(calibration)
        if self.mode == "ui":
            if not self.executor:
                raise ValueError("Calibration saver is only available in UI sessions.")
            payload = self.executor(
                "save_calibration",
                {"device": device, "calibration": to_builtins(calibration)},
            )
            if not isinstance(payload, dict):
                raise ValueError("Invalid calibration save payload.")
            saved_path = payload.get("path")
            if not isinstance(saved_path, str):
                raise ValueError("Invalid calibration save payload.")
            path = saved_path
        else:
            path = None
        return {"device": device, "calibration_name": calibration.calibration_name, "path": path}

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
        if self.session.step_id == "complete" and "complete" in self.step_registry:
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
        return steps.info("Calibration ended", "This calibration session has ended.")

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

    def advance(self, inputs: dict[str, object]) -> CalibrationStep:
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
        minimum: Int | None = None,
        maximum: Int | None = None,
        default: Int | None = None,
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
            title="Calibration complete!",
            metadata={"result": result},
        )


fields = FieldBuilder()
steps = StepBuilder()


def _render_chart_for_cli(chart: dict[str, object]) -> None:
    title = chart.get("title", "")
    x_label = chart.get("x_label", "")
    y_label = chart.get("y_label", "")
    series = chart.get("series")
    if not isinstance(series, list):
        return
    multiple_series = len(series) > 1
    for entry in series:
        if not isinstance(entry, dict):
            continue
        points = entry.get("points", [])
        if not isinstance(points, list):
            continue
        x_vals: list[float] = []
        y_vals: list[float] = []
        for point in points:
            if not isinstance(point, dict):
                continue
            x_val = point.get("x")
            y_val = point.get("y")
            if isinstance(x_val, (int, float)) and isinstance(y_val, (int, float)):
                x_vals.append(float(x_val))
                y_vals.append(float(y_val))
        if not x_vals or not y_vals:
            continue
        entry_title = str(title) if isinstance(title, str) else ""
        if multiple_series:
            label = entry.get("label", entry.get("id", "series"))
            entry_title = f"{entry_title} - {label}" if entry_title else str(label)
        curve_callable = None
        curve = entry.get("curve")
        if isinstance(curve, dict):
            curve_type = curve.get("type")
            coeffs = curve.get("coefficients")
            if curve_type in {"poly", "spline"} and isinstance(coeffs, list):
                curve_callable = curve_to_callable(curve_type, coeffs)
        plot_data(
            x_vals,
            y_vals,
            entry_title or "Calibration progress",
            str(x_label),
            str(y_label),
            interpolation_curve=curve_callable,
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
        if isinstance(chart, dict):
            _render_chart_for_cli(chart)
    click.echo()


def run_session_in_cli(step_registry: StepRegistry, session: CalibrationSession) -> list[Any]:
    engine = SessionEngine(step_registry=with_terminal_steps(step_registry), session=session, mode="cli")
    while engine.session.status == "in_progress":
        step = engine.get_step()
        render_step_for_cli(step)

        inputs: dict[str, object] = {}
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
        message = "This calibration session has ended."
        if status == "aborted":
            message = ctx.session.error or "This calibration session was aborted."
        elif status == "failed":
            message = ctx.session.error or "This calibration session failed."
        return steps.info("Calibration ended", message)


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
    inputs: dict[str, object],
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
