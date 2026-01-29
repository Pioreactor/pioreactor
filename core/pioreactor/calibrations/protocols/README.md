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


- Calibrations are saved under `.../storage/calibrations/` and are listed in calibration APIs/CLI.
- Estimators are saved under `.../storage/estimators/` and are not listed in calibration APIs/CLI.

## Example

The `od_fusion_standards` protocol uses the calibration session UI, but saves an estimator:

- calibrator: OD fusion fitting routine
- estimand: raw normalized voltages from 45°, 90°, 135°
- estimation: `ODFusionEstimator` YAML artifact
