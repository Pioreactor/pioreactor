# Plugin Job Patterns

Use this reference when writing or reviewing Pioreactor plugin background job Python.

## Discovery model

- Local dev plugin files live in `plugins_dev/` when `TESTING=1` and `PLUGINS_DEV` is set.
- Device plugin files live in `/home/pioreactor/.pioreactor/plugins`.
- Plugin files are imported during plugin discovery. Keep import-time side effects minimal.
- `pio run` loads plugin modules and registers module attributes whose names start with `click_`.
- Use `__plugin_name__` consistently as the plugin metadata name and the `plugin_name` passed to contrib job base classes.

## Base class choice

- Use `BackgroundJobContrib` for ordinary plugin jobs tied to an experiment.
- Use `LongRunningBackgroundJobContrib` when the job should survive across experiment boundaries, such as external log forwarding or monitoring jobs.
- Use `BackgroundJobWithDodgingContrib` when the job must pause or change behavior before and after OD readings.
- Do not use the core `BackgroundJob` class for plugin jobs.
- For dosing, LED, or temperature automations, use `$pioreactor-automations` instead of this skill.

## Minimal shape

```python
from __future__ import annotations

import click

from pioreactor.background_jobs.base import BackgroundJobContrib
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name

__plugin_name__ = "example-sensor"
__plugin_version__ = "0.1.0"


class ExampleSensor(BackgroundJobContrib):
    job_name = "example_sensor"

    published_settings = {
        "reading": {"datatype": "float", "settable": False, "unit": "AU"},
        "sample_interval_seconds": {"datatype": "float", "settable": True, "unit": "s"},
    }

    def __init__(self, unit: str, experiment: str, sample_interval_seconds: float) -> None:
        super().__init__(unit=unit, experiment=experiment, plugin_name=__plugin_name__)
        self.sample_interval_seconds = float(sample_interval_seconds)
        self.reading = float("nan")
        self.start_passive_listeners()

    def start_passive_listeners(self) -> None:
        self.subscribe_and_callback(self._handle_reading, "example_sensor/reading")

    def _handle_reading(self, message) -> None:
        self.reading = float(message.payload)

    def set_sample_interval_seconds(self, value: float) -> None:
        interval = float(value)
        if interval <= 0:
            raise ValueError("sample_interval_seconds must be > 0")
        self.sample_interval_seconds = interval

    def on_disconnected(self) -> None:
        pass


@click.command(name="example_sensor")
@click.option("--sample-interval-seconds", type=click.FloatRange(min=1.0), default=60.0)
def click_example_sensor(sample_interval_seconds: float) -> None:
    unit = get_unit_name()
    experiment = get_assigned_experiment_name(unit)

    with ExampleSensor(
        unit=unit,
        experiment=experiment,
        sample_interval_seconds=sample_interval_seconds,
    ) as job:
        job.block_until_disconnected()
```

## Published settings

- `published_settings` maps Python attributes to MQTT-published values.
- Required metadata keys are `datatype` and `settable`.
- Optional metadata keys are `unit` and `persist`.
- Supported control-plane datatypes are normally `string`, `float`, `integer`, `boolean`, and `json`.
- `state` is added by the base class and appears on MQTT as `$state`; do not add it yourself.
- Use `set_<setting>` when changing a setting requires validation, unit conversion, hardware updates, timer rescheduling, or logging.
- Keep setting names alphanumeric with underscores only.

## State and cleanup

- Use `job.set_state(job.READY)`, `job.set_state(job.SLEEPING)`, or `job.clean_up()` instead of assigning `job.state` directly.
- Use transition hooks like `on_ready_to_sleeping`, `on_sleeping_to_ready`, `on_init_to_ready`, and `on_disconnected` for side effects.
- Keep hardware and timers safe in all exit paths. Cancel `RepeatedTimer` instances and close serial, socket, PWM, or sensor handles in `on_disconnected`.
- If startup fails after the base constructor runs, the wrapped initializer attempts cleanup. Still structure code so partially initialized attributes are checked before cleanup.

## OD dodging jobs

Use `BackgroundJobWithDodgingContrib` only for jobs that need timed behavior around OD readings.

```python
from pioreactor.background_jobs.base import BackgroundJobWithDodgingContrib


class Bubbler(BackgroundJobWithDodgingContrib):
    job_name = "bubbler"

    def __init__(self, unit: str, experiment: str, enable_dodging_od: bool) -> None:
        super().__init__(
            unit=unit,
            experiment=experiment,
            plugin_name=__plugin_name__,
            enable_dodging_od=enable_dodging_od,
        )

    def initialize_dodging_operation(self) -> None:
        self.logger.debug("OD dodging enabled.")

    def initialize_continuous_operation(self) -> None:
        self.logger.debug("Running continuously.")

    def action_to_do_before_od_reading(self) -> None:
        self.stop_bubbling()

    def action_to_do_after_od_reading(self) -> None:
        self.start_bubbling()
```

Add config for dodging jobs:

```ini
[bubbler.config]
enable_dodging_od=1
pre_delay_duration=1.5
post_delay_duration=0.5
```

## Config and CLI

- Put plugin job config in `[<job_name>.config]` unless an existing plugin convention says otherwise.
- CLI options should usually be a subset of config options.
- Prefer config fallbacks so the job can start with minimal CLI arguments.
- For long-running non-experiment jobs, use `UNIVERSAL_EXPERIMENT` deliberately and explain why.
