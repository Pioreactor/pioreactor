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

A unit selects exactly one driver, so two OD devices never run together.
Future models can ship this file as their hardware default.

## One device contract

Every OD device implements `pioreactor.od_devices.ODDevice`, the built-in
photodiodes (`PhotodiodeODDevice`) included. A plugin registers a factory with
`register_od_device`; the factory receives the driver-owned `options` mapping and
a logger, validates the options, and does no acquisition. Core validates only the
outer `driver`/`options` structure; its I²C compatibility check covers built-in
hardware, not external devices.

A device declares `outputs`, one `ODSignal` per logical channel `"1"`–`"4"`:

```python
from pioreactor.structs import ODSignal

ODSignal(name="reflectance", angle="0", scale="unfiltered reflectance / optical output, API 2")
```

- `name` identifies the quantity. Photodiode outputs are named by angle (`"90"`).
- `angle` is the observation geometry: 0°, 45°, 90°, 135° or 180°.
- `scale` says what the numbers mean. It must change whenever the same `name`'s
  numbers change meaning: gain, LED intensity, firmware API, units. Photodiode
  scales record the IR LED intensity.
- `calibrated` marks outputs the device converts itself (for example the probe's
  own density). Pioreactor never calibrates those.

Outputs are declared at construction, before any acquisition. `name` and `angle`
stay fixed while the device is open; `scale` may change between reads. Channel 1
is the device's primary biomass signal.

`start()` begins acquisition or resumes it after `pause()`. Sleeping calls
`pause()`, which suspends acquisition while retaining resources. Disconnecting
calls `close()`, which ends acquisition and releases resources whether the device
is running, paused or never started. `read()` returns `None` when nothing is new,
or one acquisition:

```python
from pioreactor.structs import ODDeviceReadings

ODDeviceReadings(timestamp=acquisition_time, values={"1": value})
```

The timestamp is timezone-aware and values are finite. Optical-output correction
belongs to the device; normalization by the experiment's initial reading belongs
to Pioreactor's growth model. The device does not publish MQTT.

## The OD job owns everything after acquisition

`ODReader` schedules the device, applies calibrations, and publishes. All primary
readings (`ods`, `od1`–`od4`) use one `ODReading` shape: `timestamp`, `od`,
`channel`, `angle` and `calibrated` (`0` or `1`). A calibrated channel also
publishes its uncalibrated value on `raw_od<channel>` in the same shape, and the
leader stores it with its angle in `raw_od_readings`. `source` is the driver name.

`record()` reads once; `snapshot()` waits for fresh data. Python callers normally
use `start_od_reading(interval=5)`, which selects the hardware. `interval=None`
leaves sampling manual. `start_photodiode_od_reading(channels, ...)` and
`start_external_od_reading(...)` take explicit options; both accept
`calibration=True` (active calibrations), `False` (device values), or explicit
calibrations. `ExternalODReader` polls a plugin that acquires on its own;
`PhotodiodeODReader` adds Eye-spy settings, scheduled acquisition and fusion.

`PhotodiodeODDevice` keeps Eye-spy's illumination, ADC, reference correction,
blanking and fusion together, because fusion combines its angles and blanking
corrects its raw voltages. Blanking, fusion calibration, OD dodging and the
photodiode self-tests reject or skip external devices.

## Calibrations

Calibrations are stored per signal, at `od_calibration_device(driver, name)`:
`od90` for photodiodes, `od_<driver>_<name>` otherwise (for example
`od_turbidvision_reflectance`). The job loads the active calibration of each
output's signal and binds it before the device starts.

Invariants, checked when binding and again on every reading:

- A calibration only applies to the driver and signal it was fit on.
- A calibration only applies on the scale it was fit on. A firmware rescale or
  an IR LED intensity change stops calibrated publishing with an error instead of
  publishing wrong OD.
- A device-calibrated output is never calibrated again.
- Signals outside the standards' range clamp to it.

The OD600 standards protocol measures whichever hardware the unit selects. On an
external driver its target is `od_<driver>`:

```sh
pio calibrations run --device od_turbidvision
```

Starting a session needs no hardware; the first measurement discovers the
device's uncalibrated outputs and their scales, and later measurements must match
them. It saves one `ExternalODCalibration` per output, recording `driver`,
`signal` and `signal_scale`. The turbidostat's `auto` biomass signal resolves to
`od` when one of the driver's signals is calibrated, and follows channel 1.

## Storage and charts

The upcoming update adds `angle` to `raw_od_readings`. Older photodiode workers'
`raw_od*` payloads still parse. Growth processing uses `ods`, rather than
photodiode fusion, for external devices. When switching hardware, start a new
experiment or clear its normalization cache; the growth model does not detect
hardware changes.

OD charts use observation geometry, not the current photodiode configuration.
The time-series API includes `angle` on each OD point; live charts use the MQTT
reading's `angle`. Historical raw points predating the migration have
`angle: null` and are labeled by channel. Upgrade the leader before using a
plugin.
