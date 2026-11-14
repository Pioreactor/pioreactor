# Protocols

Protocols are interactive, step-driven flows that collect measurements and produce an artifact.
Historically, that artifact was always a calibration. Protocols now also support producing
estimators (for example, the OD fusion estimator). The protocol/session flow is the same; only
the saved artifact differs.

## Terminology

- protocol: the step-by-step workflow that collects the data needed to produce an artifact.
- fitting routine: the code that turns the collected protocol data into artifact parameters.
- calibration: a saved mapping between measured and target variables.
- estimator: a saved model applied to sensor readings to produce a derived measurement.
- estimation: the derived measurement produced by applying an estimator.
- estimand: the quantity an estimator is intended to recover.

## How protocols produce artifacts

- Calibrations are saved under `.../storage/calibrations/` and are listed in calibration APIs/CLI.
- Estimators are saved under `.../storage/estimators/` and are listed in estimators APIs/CLI.

## Example

The `od_fusion_standards` protocol uses the calibration session UI, but saves an estimator:

- fitting routine: OD fusion fitting routine
- estimator inputs: normalized readings from 45°, 90°, and 135°
- saved estimator: `ODFusionEstimator` YAML artifact
- estimation: the fused OD value produced when the artifact is applied


## Waiting for a condition

Return `steps.wait(title, body, poll_interval_s=5.0)` from a step's `render()`
to wait without asking the user to click Continue. Its `advance()` should perform
one short, bounded check and return `None` while waiting or the next step once
ready. Persist observations in `ctx.data`; keep `render()` free of side effects.
The browser polls sequentially, displays progress, and permits only Abort while
waiting. Reloading resumes from the saved observations. The CLI performs the same
checks without prompting (Ctrl-C interrupts it).

Wait steps use the existing asynchronous inputs endpoint. They do not hold a Huey
worker for the entire waiting period. Protocols own their readiness conditions,
sensor freshness checks, timeouts, and resource cleanup. Browser-driven polling
stops while the browser is closed; hardware jobs have their own lifecycle.

## Reproducible calibration artifacts

Every saved calibration YAML must contain the measurements and fit parameters
that created its curve. Keep all recorded rows in their original order, and use
`included` to select the observations used for fitting; absent or null means all
rows are included. Exclusion never deletes measurements. Curve coefficients
retain the polynomial degree; spline artifacts retain their knot positions. Do
not introduce implicit anchor constraints or external weighting state.

Saved-calibration edits compute a valid candidate before atomically replacing
the artifact. Running activities keep their loaded calibration; restart them to
use a saved edit.

The saved-calibration editor permits corrections to both `recorded_data.x` and
`recorded_data.y` for every calibration type. Row order remains unchanged.
Corrections overwrite the previous values only after validating their count and
finiteness and successfully recalculating the curve. No editable-column metadata
is stored. For spline fits, changing included x coordinates relocates knots using
the saved knot count; the new positions are persisted with the curve.
