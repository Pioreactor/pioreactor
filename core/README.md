# Core runtime

## Model-selected OD acquisition

The native `od_reading` activity selects its acquisition implementation through
`hardware.py`, using the existing HAT → model YAML layering. Missing `od.yaml`
means the existing photodiode/ADC path. A local model override can select an
add-on without changing the unit's model identity:

```yaml
# $DOT_PIOREACTOR/hardware/models/<model_name>/<model_version>/od.yaml
driver: turbidvision
bus: 1
address: 0x69
```

A future model can ship the same file as its default hardware definition. Model
capacity, physical dimensions and operating limits remain in `models.py`.

A plugin registers its acquisition factory with
`pioreactor.od_sources.register_od_source(name, factory)`. The factory receives
`ODHardwareConfig` and a logger. Its source implements `start`, `stop`, `read`,
`close` and exposes `signal_unit`. `read` returns a fresh optical-power-normalized
ratio or `None` for no new sample. The current external source is a single
backscatter channel at 0 degrees. The driver owns I²C, quality validation,
duplicate detection and shutdown; it does not own MQTT or experiment normalization.

`ODReadingJob` owns scheduling, iteration and publication. `ODReader` retains
photodiode-specific acquisition, blank correction and calibration/fusion.
`ExternalODReader` uses the plugin source and the same native activity lifecycle.
Python callers and the CLI use the same `start_od_reading` selection point.

External acquisition is continuous: its polling interval is not an exposure
window. It publishes no scheduled `first_od_obs_time`; OD dodging and stirring's
scheduled-OD avoidance are disabled for it. Native photodiode blanking and
calibration reject this source, and photodiode self-tests are omitted. Hardware
compatibility checks retain HAT auxiliary ADC requirements but replace the PD
ADC requirements with the configured probe address.

External readings use the tagged `SensorODReading` MQTT shape, including source,
signal units and the actual backscatter angle `0`. The existing `od_readings`
table stores the value and angle without a schema change. Source and unit fields
are available in MQTT, not additional database columns. Chart history recognizes
angle 0 independently of the unit's photodiode channel config, and preserves small
reflectance values. This is a ratio, not a voltage or calibrated OD600.

Growth processing uses `ods`, never a photodiode fusion estimator for this source.
Normalization records the source name alongside its cached factors; switching
source requires a new experiment or explicitly clearing the normalization cache.
