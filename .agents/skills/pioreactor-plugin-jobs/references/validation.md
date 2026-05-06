# Validation

Use this reference before reporting a Pioreactor plugin job complete.

Before choosing commands, read `development-environments.md`. Repo-local development and on-device development have different validation surfaces.

## Environment-aware strategy

- Repo-local development has the cloned source tree, `.venv`, and pytest, but usually no real Pioreactor hardware.
- On-device development has hardware and real Pioreactor services, but usually not pytest or the full repo checkout.
- If local tests pass but the job touches hardware, report the remaining on-device smoke check explicitly.
- If working directly on a Pioreactor, do not require repo-only pytest checks; use plugin discovery, runtime, MQTT, logs, API descriptors, and hardware behavior instead.

## Discovery checks

Run discovery before runtime checks:

```bash
.venv/bin/pio plugins list
```

This catches plugin import errors and metadata problems. If the command does not include the plugin or prints a plugin load error, fix discovery before trying to run the job.

Confirm the command is registered:

```bash
.venv/bin/pio run --help
```

The command list should include the plugin job's Click command name.

## Runtime smoke check

Start the job with the narrowest realistic command:

```bash
.venv/bin/pio run <job_name> [OPTIONS]
```

For blocking jobs, run in a separate terminal or an agent background session. Then inspect MQTT:

```bash
.venv/bin/pio mqtt -t "pioreactor/+/+/<job_name>/#"
```

Look for:

- `$state` reaching `ready`.
- Expected metadata and published settings.
- Published setting values changing when callbacks, timers, or setters run.
- Empty retained messages on cleanup for non-persistent settings.

Stop the job with Ctrl-C, `pio kill --job-name <job_name>`, or a `$state/set` message as appropriate, then confirm cleanup behavior.

## UI descriptor check

After adding `$DOT_PIOREACTOR/plugins/ui/jobs/<file>.yaml`, check a descriptor endpoint:

```bash
curl -fsS http://127.0.0.1:4999/unit_api/jobs/descriptors
```

For worker-only plugin jobs, use the leader proxy:

```bash
curl -fsS http://127.0.0.1:4999/api/workers/<unit>/jobs/descriptors
```

Confirm:

- The descriptor appears once.
- `job_name` matches Python and Click.
- Visible settings have labels.
- YAML `published_settings[].key` values match Python `published_settings`.

If a descriptor is missing, check `DOT_PIOREACTOR`, YAML syntax, and `pioreactor.log` for `Yaml error in ...`.

## Tests

- Prefer targeted import or unit tests for pure helpers.
- Use `.venv/bin/pytest <specific file or test>` for repo tests only in repo-local development.
- Keep MQTT/job-manager-backed tests serial; concurrent pytest runs can create noisy shared-state failures.
- Do not run the full test suite for ordinary plugin job changes.
- On-device, skip pytest unless the user has explicitly installed and configured a test checkout there.
