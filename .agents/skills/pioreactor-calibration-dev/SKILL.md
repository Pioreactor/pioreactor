---
name: pioreactor-calibration-dev
description: Create or update Pioreactor calibration routines and session flows in core/pioreactor/calibrations, including CLI + UI behavior, step registries, and protocol registration.
---

# Pioreactor Calibration Dev

## When to use
Use this skill when adding or modifying calibration protocols, session steps, or calibration CLI/UI flows.

## High-level terminology

0. A calibration relates two variables together. One variable is what we can vary and the other is the target.
1. The calibration relates them via a calibration curve, which is a mapping between the variables.
1. The Pioreactor has many devices that can be calibrated. A device can have multiple calibrations, but only one can be active at a time.
2. A protocol creates a calibration for a device. Devices can have multiple protocols.
1. A calibration can apply to multiple devices. Example: the same calibration can be used for waste and media pumps.

In practice, calibrations are stored as YAML files in `~/.pioreactor/storage/calibrations/<device>/`.

## Tools
- Use `scripts/generate_calibration_flow_graphs.py` to generate protocol directed graphs.

## Registries (authoritative maps)
- `calibration_protocols` in `core/pioreactor/calibrations/registry.py`: maps `device -> protocol_name -> CalibrationProtocol class`. Populated on subclassing.
- `StepRegistry` in `core/pioreactor/calibrations/session_flow.py`: maps `step_id -> SessionStep class` per protocol.
- `calibration_actions` in `core/pioreactor/web/tasks.py`: maps `action_name -> handler` that returns a Huey task, label, and normalizer.

## Workflow
1. Confirm target device and protocol name.
2. Implement calibration routine to return the correct `structs.*Calibration` type.
3. Define session steps as `SessionStep` subclasses with `step_id`, `render(ctx) -> CalibrationStep`, and `advance(ctx) -> SessionStep | None`.
4. Provide a `StepRegistry` mapping `{step_id: StepClass}` for the protocol.
5. Expose:
   - `start_<protocol>_session(...) -> CalibrationSession`
6. Define a `CalibrationProtocol` subclass with:
   - `target_device`, `protocol_name`
   - `title`, `description`, `requirements` for the UI protocol list
   - `step_registry` and `start_session(...)`
   - optional `on_session_abort(session, executor=None)` for cleanup when UI abort is pressed
7. Register the protocol in `core/pioreactor/calibrations/__init__.py` and CLI entrypoint if required.
8. The UI protocol list is served by `/api/workers/<unit>/calibration_protocols` (task response). There is no static frontend registry anymore. Update the frontend only if new step types are required.

## Session Flow (UI + API)
- Session engine: `core/pioreactor/calibrations/session_flow.py`.
- Steps are classes, not functions. Keep each `render` and `advance` single-purpose.
- Use `SessionContext` for `ctx.data` and `ctx.complete(...)` results.
- Store calibrations via `ctx.store_calibration(calibration, device)` so UI can link.
- Store estimators via `ctx.store_estimator(estimator, device)` so UI can link.
- `ctx.read_voltage()` uses the `read_aux_voltage` action.
- For UI sessions, hardware actions must run in Huey tasks via `SessionContext.executor`.
- `_execute_calibration_action` uses the `calibration_actions` registry with a fixed 300s timeout.

## Persistence Contract (Critical)
- Treat persistence from `SessionStep.advance()` as mode-sensitive:
  - UI mode runs in Flask (`www-data` context).
  - Huey tasks run as `pioreactor` and are the correct place for privileged writes.
- In UI sessions, always persist through `SessionContext` helpers:
  - calibrations: `ctx.store_calibration(calibration, device)`
  - estimators: `ctx.store_estimator(estimator, device)`
- Do not call `save_to_disk_for_device(...)` directly from UI `SessionStep.advance()`.
- Do not call `set_as_active_calibration_for_device(...)` directly from UI `SessionStep.advance()`.
- Why: direct writes from UI steps can create ownership drift (`www-data`-owned YAMLs) and bypass the session executor/action pipeline.
- Call chain (UI):
  - `ctx.store_calibration` / `ctx.store_estimator`
  - `unit_calibration_sessions_api._execute_calibration_action(...)`
  - `core/pioreactor/web/tasks.py` registered action (`save_calibration` / `save_estimator`)
  - `*.save_to_disk_for_device(...)` in Huey task context
- CLI sessions have no executor; direct save/set-active is acceptable there.
- Recommended branch pattern:

```python
if ctx.mode == "ui":
    save_result = ctx.store_estimator(estimator, device)
    saved_path = save_result["path"]
else:
    saved_path = estimator.save_to_disk_for_device(device)
    estimator.set_as_active_calibration_for_device(device)
```

- If you introduce a new persisted artifact type, register a calibration action in `core/pioreactor/web/tasks.py` and route persistence through the executor in UI mode.

## Abort Cleanup Hook (`on_session_abort`)
- `CalibrationProtocol` supports optional:
  - `@classmethod`
  - `def on_session_abort(cls, session: CalibrationSession, executor=None) -> None`
- This is invoked by the unit calibration session abort route before the session is marked `aborted`.
- Prefer graceful, cooperative shutdown over process killing:
  - publish `b"disconnected"` to `pioreactor/<unit>/<experiment>/<job_name>/$state/set`
  - avoid PID-based `kill` for jobs launched within Huey task workers.
- If your protocol starts jobs via `/unit_api/jobs/run/job_name/...`, store the exact experiment used in `session.data`. Also specify the JOB_SOURCE in the payload:

  ```
    experiment = get_testing_experiment_name()
    job_source = f"fir_bias_trim_{session_id}"

    payload = {
        "args": [],
        "options": {
            "automation_name": "thermostat",
            "target_temperature": target_temperature,
        },
        "env": {
            "EXPERIMENT": experiment,
            "JOB_SOURCE": job_source,
        },
        "config_overrides": [],
    }
    response = post_into(
        address,
        "/unit_api/jobs/run/job_name/temperature_automation",
        json=payload,
        timeout=8,
    )
  ```


- Aggregate cleanup failures into one `ValueError` message when multiple resources fail to stop, so the abort route can surface useful diagnostics.

## Field builders for forms in `SessionStep`

Protocol steps build forms using `fields.*` helpers from `session_flow.py`. These correspond to
`SessionInputs.*` accessors used in `advance()` methods.

- `fields.str(name, label=None, default=None)` -> `ctx.inputs.str(name, default=..., required=...)`
  - `field_type`: `string`
  - Use for names, labels, and free-form text.
- `fields.choice(name, options, label=None, default=None)` -> `ctx.inputs.choice(...)`
  - `field_type`: `choice`
  - Validates input against the provided options.
- `fields.float_list(name, label=None, default=None)` -> `ctx.inputs.float_list(...)`
  - `field_type`: `float_list`
  - Accepts a list of numbers or a comma-separated string.
- `fields.bool(name, label=None, default=None)` -> `ctx.inputs.bool(...)`
  - `field_type`: `bool`
  - Accepts true/false and common yes/no string inputs.
- fields.float(name, label=None, minimum=None, maximum=None, default=None) -> ctx.inputs.float(...)
   - field_type: float
   - Enforces numeric bounds when provided.
   - Supports custom bound errors: min_error_msg and max_error_msg (stored on CalibrationStepField).
- fields.int(name, label=None, minimum=None, maximum=None, default=None) -> ctx.inputs.int(...)
   - field_type: int
   - Enforces integer bounds when provided.
   - Supports custom bound errors: min_error_msg and max_error_msg (stored on CalibrationStepField).



## Terminal Steps
- Terminal steps are auto-included by `get_session_step`, `advance_session`, and `run_session_in_cli`.
- Use `ctx.complete(...)` to finish; `CalibrationComplete` renders the result.
- Use `ctx.abort(...)` or `ctx.fail(...)` to end early; `CalibrationEnded` renders the message.

## Chart Snapshots
- Use `step.metadata.chart` with:
  - `title`, `x_label`, `y_label`
  - `series: [{ id, label, points, curve? }]` and `points: [{x, y}]`
  - Optional `curve: { type: "poly", coefficients: [...] }`
- UI renders in `frontend/src/components/CalibrationSessionChart.jsx`.
- CLI renders via plotext using `plot_data` in `core/pioreactor/calibrations/utils.py`.
- Optional curve: { type: "spline", coefficients: [knots, coeffs] } where knots is the x‑knot list and coeffs is per‑interval cubic
    coefficients.


## Loading animations for calibration steps

  - Any SessionStep.render() can add step.metadata.loading_images as a list of { src, alt, caption? }.
  - The UI (frontend/src/components/CalibrationSessionDialog.jsx) cycles these frames while sessionLoading is true (after a 250 ms delay). Only one of loading_images or image is shown, and charts/tables are hidden during loading.
  - Frame rate is controlled in the dialog via setInterval(...) (ms per frame).
  - SVG frame assets live under core/pioreactor/web/static/svgs/ (and optionally frontend/public/svgs/ if reused by the frontend
    directly).



## CLI UX Rules (Must Follow)
- Use `pioreactor.calibrations.cli_helpers`: `info`, `info_heading`, `action`, `action_block`, `green`, `red`.
- Prompts are green with `prompt_suffix=" "` and no trailing colon.
- Physical steps go in `action_block` with blank lines around them.
- Keep calibration output unchanged (computed results, data structures).

## Field Bound Validation (UI + CLI)
- Bounds are validated in the session engine before `advance()` using the step’s `fields` definitions.
- Prefer defining `minimum`/`maximum` (and error messages) on the field and calling `ctx.inputs.float("name")` /
`ctx.inputs.int("name")`
 without repeating bounds in `advance()`. This keeps a single source of truth.

## Metadata Tables (UI)
- Use `step.metadata.table` to render small progress tables in the calibration dialog.
 - Shape: `{ title?: str, columns?: list[str], rows?: list[list|dict], empty_message?: str }`
 - Rows can be arrays (positional) or dicts (values are rendered in Object.values order).
- Tables render in `frontend/src/components/CalibrationSessionDialog.jsx` and appear above the step body.



## Hardware Access (Huey)
- Web API runs as `www-data`; hardware access must be in Huey.
- Register actions in `core/pioreactor/web/tasks.py` via `register_calibration_action`.
- Actions return `(task, label, normalizer)` and are dispatched via `_execute_calibration_action`.
- This same action path is the required persistence path for UI session writes.

## Implementation Checklist
- Guard against running jobs with `is_pio_job_running` when appropriate.
- Capture metadata with `get_unit_name`, `get_testing_experiment_name`, `current_utc_datetime`.
- Use existing helpers in `core/pioreactor/calibrations/utils.py` for curve fitting.
- Adding a new Step? Make sure to add it to the StepRegistry associated.
- In UI step code, never directly call `save_to_disk_for_device` / `set_as_active_calibration_for_device`; use `ctx.store_calibration` / `ctx.store_estimator`.
- Use existing helpers in core/pioreactor/calibrations/utils.py for curve fitting and curve_to_callable.
- For spline fits, use pioreactor.utils.splines.spline_fit and store curve_type="spline" with the [knots, coefficients] payload.

## Tests
- Use pytest with a specific file or directory, e.g. `pytest core/tests/web/` (activate venv first).
