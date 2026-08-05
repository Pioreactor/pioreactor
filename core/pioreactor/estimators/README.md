# Estimators

Estimators are saved artifacts used to transform or combine sensor data into a derived measurement.
They are similar to calibrations in terms of lifecycle (created via a protocol flow, saved to disk,
optionally marked active), but are not calibrations. They are managed through the separate estimators
UI and `pio estimators` CLI rather than through the calibrations UI/CLI.

## Terminology

- protocol: the step-by-step workflow that collects the data needed to produce or update an estimator.
- fitting routine: the code that turns the collected protocol data into estimator parameters.
- estimator: the saved model or artifact applied to sensor readings to produce a derived measurement.
- estimation: the derived measurement produced by applying an estimator.
- estimand: the quantity the estimator is intended to recover.

## Storage

Estimators are stored under:

- `$DOT_PIOREACTOR/storage/estimators/<device>/<estimator_name>.yaml`

The active estimator for a device is tracked in `active_estimators` persistent storage.

## Current estimators

- `od_fused`: ODFusionEstimator produced by the `od_fusion_standards` protocol (full fit) or the
  `od_fusion_offset` protocol (single-point offset). This estimator fuses 45°, 90°, and 135°
  OD sensor readings into a single fused OD value.

## Usage (Python)

```python
from pioreactor import types as pt
from pioreactor.estimators import load_active_estimator
from pioreactor.utils.od_fusion import compute_fused_od

estimator = load_active_estimator(pt.OD_FUSED_DEVICE)
if estimator is not None:
    fused = compute_fused_od(estimator, readings_by_angle)
```

## UI flow

Estimator creation uses the shared calibration-session machinery from the Protocols page. On
completion, the session engine calls the `save_estimator` action, which uses
`EstimatorBase.save_to_disk_for_device` and `EstimatorBase.set_as_active_calibration_for_device` to
persist the estimator YAML and mark it active for the device. Once saved, the artifact is managed
through the separate Estimators UI and `pio estimators`; it does not appear in the calibrations
UI or CLI.

## Notes

- Estimators are created via calibration-like protocol flows and saved through the session executor
  action `save_estimator`.
- Estimators are intentionally not listed by the calibrations API or CLI.
