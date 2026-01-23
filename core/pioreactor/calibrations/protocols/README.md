# Protocols

Protocols are interactive, step-driven flows that collect measurements and produce an artifact.
Historically, that artifact was always a calibration. Protocols now also support producing
estimators (for example, the OD fusion estimator). The protocol/session flow is the same; only
the saved artifact differs.

## Terminology

- protocol: the step-by-step workflow that collects data and runs a calibrator or estimator.
- calibrator <-> estimator: the function or routine that accepts data and produces an artifact.
- calibrations <-> estimations: the resulting artifact produced by a calibrator or estimator.
- calibrand <-> estimand: the object being transformed by the calibrator or estimator.

## How protocols produce artifacts

Protocols define a step registry and are executed through a `CalibrationSession`. During the flow,
protocol steps call one of:

- `ctx.store_calibration(...)` to persist a calibration artifact, or
- `ctx.store_estimator(...)` to persist an estimator artifact.

Both run through the same session engine and UI, but they store into different backends and are
surfaced differently:

- Calibrations are saved under `.../storage/calibrations/` and are listed in calibration APIs/CLI.
- Estimators are saved under `.../storage/estimators/` and are not listed in calibration APIs/CLI.

## Field builders

Protocol steps build forms using `fields.*` helpers from `session_flow.py`. These correspond to
`SessionInputs.*` accessors used in `advance()` methods.

- `fields.str(name, label=None, default=None)` -> `ctx.inputs.str(name, default=..., required=...)`
  - `field_type`: `string`
  - Use for names, labels, and free-form text.
- `fields.float(name, label=None, minimum=None, maximum=None, default=None)` -> `ctx.inputs.float(...)`
  - `field_type`: `float`
  - Enforces numeric bounds when provided.
- `fields.int(name, label=None, minimum=None, maximum=None, default=None)` -> `ctx.inputs.int(...)`
  - `field_type`: `int`
  - Enforces integer bounds when provided.
- `fields.choice(name, options, label=None, default=None)` -> `ctx.inputs.choice(...)`
  - `field_type`: `choice`
  - Validates input against the provided options.
- `fields.bool(name, label=None, default=None)` -> `ctx.inputs.bool(...)`
  - `field_type`: `bool`
  - Accepts true/false and common yes/no string inputs.
- `fields.float_list(name, label=None, default=None)` -> `ctx.inputs.float_list(...)`
  - `field_type`: `float_list`
  - Accepts a list of numbers or a comma-separated string.

## Example

The `od_fusion_standards` protocol uses the calibration session UI, but saves an estimator:

- calibrator: OD fusion fitting routine
- estimand: raw normalized voltages from 45°, 90°, 135°
- estimation: `ODFusionEstimator` YAML artifact
