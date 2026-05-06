# UI Job Descriptors

Use this reference when a plugin background job should appear in the Pioreactor UI.

## Location and loading

- Plugin job descriptors live under `$DOT_PIOREACTOR/plugins/ui/jobs/*.yaml`.
- Built-in job descriptors live under `$DOT_PIOREACTOR/ui/jobs/*.yaml`.
- The loader reads built-ins first and plugins second; duplicate `job_name` entries are overwritten by the later file.
- Unit-local descriptors are served by `/unit_api/jobs/descriptors`.
- Leader-local descriptors are served by `/api/jobs/descriptors`.
- Worker-specific descriptors are proxied through `/api/workers/<unit>/jobs/descriptors`.
- Worker-only plugin jobs should be checked through the worker-specific endpoint, not only the leader-local endpoint.

## Schema

Match `BackgroundJobDescriptor`:

```yaml
display_name: Example sensor
job_name: example_sensor
display: true
source: example-sensor
description: Read an example sensor continuously.
published_settings:
  - key: reading
    label: Reading
    type: numeric
    unit: AU
    display: true
    description: Latest sensor reading.
    editable: false
  - key: sample_interval_seconds
    label: Sample interval
    type: numeric
    unit: s
    display: true
    description: Seconds between sensor reads.
    editable: true
    min: 1
```

Descriptor fields:

- `display_name`: human-facing name.
- `job_name`: must match the Python class `job_name` and the `pio run` command.
- `display`: set `true` for jobs users should see.
- `source`: usually `__plugin_name__` or a short plugin name.
- `description`: include when `display` is true.
- `published_settings`: UI representation of settings from the Python job.

Published setting descriptor fields:

- `key`: must match a Python `published_settings` key.
- `type`: one of `numeric`, `boolean`, `string`, or `json`.
- `display`: whether to show this setting.
- `label`: required in practice for displayed fields.
- `description`: helpful for visible fields.
- `unit`: optional display unit.
- `editable`: set `false` for read-only values. Runtime mutability is still governed by Python `published_settings[...]["settable"]`.
- `min` and `max`: optional numeric bounds for UI controls.

## Consistency checks

- Python `published_settings` uses `datatype`; UI YAML uses `type`.
- Python uses `settable`; UI YAML uses `editable`.
- Keep read-only measurements read-only in both places: Python `settable: False`, YAML `editable: false`.
- Do not expose a YAML setting that the job never publishes.
- Do not rely on YAML alone to make a setting mutable; implement a Python `set_<setting>` method if setting changes need side effects.
