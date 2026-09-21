# Core runtime

## Model-selected OD acquisition

The native `od_reading` activity selects its device through the existing
HAT → model hardware YAML layering. Built-in 20/40 ml models ship `od.yaml`
with `driver: photodiodes`. The update installs missing defaults on leaders and
workers without overwriting existing selections. Missing `od.yaml` still selects
Eye-spy for compatibility with older installations.
An add-on keeps the unit's existing model identity:

```yaml
# $DOT_PIOREACTOR/hardware/models/<model_name>/<model_version>/od.yaml
driver: turbidvision
options:
  bus: 1
  address: 0x69
```

Future models can ship this file as their hardware default.

## External device contract

A plugin registers a factory with `pioreactor.od_devices.register_od_device`.
The factory receives the driver-owned `options` mapping and a logger. The driver
validates its options before opening hardware and checks connectivity at startup.
Core validates only the outer `driver`/`options` structure; its I²C compatibility
check covers built-in hardware, not external devices. Options follow the existing
HAT → model dictionary merging.

The device implements `start`, `read`, `pause`, and `close`, and declares `source`
and `angle`. Geometry is fixed for the device lifetime: Turbid Vision declares
`angle = "0"`; other devices can declare the supported 45°, 90°, 135°, or 180°
geometries without changing photodiode calibration types.

`start()` begins acquisition or resumes it after `pause()`. Sleeping calls
`pause()`, which suspends acquisition while retaining resources for resuming.
Disconnecting calls `close()`, which ends acquisition and releases resources
whether the device is running or paused.

`read()` returns `None` for no fresh measurement, or:

```python
from pioreactor.structs import ODDeviceReading

ODDeviceReading(timestamp=acquisition_time, value=value, calibrated=False)
```

The timestamp is a timezone-aware datetime. The value is one consistently
selected optical signal. Optical-output correction belongs to the device;
normalization by the experiment's initial reading belongs to Pioreactor's growth
model. `calibrated` describes whether the device applied a calibration to the
returned value; it does not request another Pioreactor calibration. Select the
output at startup and keep it fixed through sleep/resume. The device does not
publish MQTT or provide growth estimates.

All primary MQTT readings use one `ODReading` shape: `timestamp`, `od`,
`channel`, `angle`, and `calibrated` (`0` for uncalibrated, `1` for calibrated).
The integer flag is an ordinary field, preserving the existing MQTT encoding.
There is no discriminator or hardware-specific
metadata on `ods` or `od1`–`od4`. The source remains a job setting. Eye-spy keeps
illumination and calibration-name metadata in its internal processing readings
and the existing `raw_od*` / `calibrated_od*` diagnostic topics.

External readings use logical channel 1 and the device-declared geometry. There
is no external channel configuration, multi-output contract, or scheduled-acquisition
capability. External devices are polled for their latest reading; OD dodging and
stirring's scheduled-OD avoidance remain specific to Eye-spy.

## Shared activity, separate acquisition

`ODReader` owns scheduling, callbacks, iteration, MQTT publication, and lifecycle.
`record()` reads once; `snapshot()` waits for fresh data. Python callers normally
use `start_od_reading(interval=5)`, which selects hardware and loads configured
photodiode channels and processing defaults. `interval=None` leaves sampling
manual. Calibration, blanking, and tests that need explicit channel mappings or
processing overrides use `start_photodiode_od_reading(channels, ...)`. Its options
are keyword-only after `channels`. Direct reader construction takes a device
factory, unit, experiment, and interval. `ExternalODReader` wraps plugin observations, while
`PhotodiodeODReader` specializes the shared job for
Eye-spy settings, acquisition timing, calibration failures, and diagnostics.
The two concrete readers inherit `ODReader` and use the same activity name and
primary MQTT topics. The plugin protocol is named `ExternalODDevice`; Eye-spy
has its own acquisition interface.

`PhotodiodeODDevice` keeps Eye-spy's multiple channels, illumination, ADC,
reference correction, blanking, calibration, and fusion together. Its diagnostics
use the existing photodiode message types, not a generic optional-fields blob.
External devices never enter this pipeline. Photodiode-specific blanking and
calibration reject external devices, and photodiode self-tests are omitted.

The OD job publishes its source separately. Existing SQL tables store the
value and angle. The upcoming update adds `angle` to `raw_od_readings`. The chart
preserves small reflectance values. Growth processing uses `ods`, rather than photodiode fusion, for the
external device. When switching hardware, start a new experiment or clear its
normalization cache; the growth model does not detect hardware changes.

OD charts use observation geometry, not the current photodiode configuration.
The time-series API includes `angle` on each OD point; live charts use the MQTT
reading's `angle`. Both OD and raw diagnostic history read geometry directly
from their stored observations. Historical raw points predating the migration have `angle: null`
and are labeled by channel. Upgrade the leader before using the plugin.
