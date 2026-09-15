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
bus: 1
address: 0x69
```

Future models can ship this file as their hardware default.

## External device contract

A plugin registers a factory with `pioreactor.od_devices.register_od_device`.
The factory receives `ODHardwareConfig` and a logger. Its device implements
`start`, `read`, `stop`, and `close`, and declares `source` and `signal_unit`.

`read()` returns `None` for no fresh measurement, or:

```python
from pioreactor.structs import ODDeviceReading

ODDeviceReading(timestamp=acquisition_time, value=reflectance)
```

The timestamp is a timezone-aware datetime. The value is one consistently
selected optical signal. Optical-output correction belongs to the device;
normalization by the experiment's initial reading belongs to Pioreactor's growth
model. The device does not publish MQTT or provide growth estimates.

External readings use channel 1 and the actual 0° backscatter geometry. There is
no external channel configuration, multi-output contract, or scheduled-acquisition
capability. External devices are polled for their latest reading; OD dodging and
stirring's scheduled-OD avoidance remain specific to Eye-spy.

## Shared activity, separate acquisition

`ODReader` owns scheduling, callbacks, iteration, MQTT publication, and lifecycle.
`record()` reads once; `snapshot()` waits for fresh data. Python callers normally
use `start_od_reading`; direct construction takes a device factory, unit,
experiment, and interval. `ExternalODReader` wraps plugin observations, while
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

External MQTT readings include source and units. Existing SQL tables store the
value and angle. The upcoming update adds `angle` to `raw_od_readings`. The chart
preserves small reflectance values. Growth processing uses `ods`, rather than photodiode fusion, for the
external device. When switching hardware, start a new experiment or clear its
normalization cache; the growth model does not detect hardware changes.

OD charts use observation geometry, not the current photodiode configuration.
The time-series API includes `angle` on each OD point; live charts use the MQTT
reading's `angle`. Both OD and raw diagnostic history read geometry directly
from their stored observations. Historical raw points predating the migration have `angle: null`
and are labeled by channel. Upgrade the leader before using the plugin.
