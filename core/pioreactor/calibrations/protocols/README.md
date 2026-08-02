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
