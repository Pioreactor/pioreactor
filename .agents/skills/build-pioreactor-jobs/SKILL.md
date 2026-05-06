---
name: build-pioreactor-jobs
description: Build Pioreactor plugin background jobs, including file-based plugin modules, BackgroundJobContrib or LongRunningBackgroundJobContrib classes, pio run command registration, published settings, MQTT listeners, cleanup hooks, OD-dodging jobs, local discovery through PLUGINS_DEV, and UI job descriptors under plugins/ui/jobs. Use when Codex is asked to create, update, debug, or review a Pioreactor plugin job or make a custom job appear in the Pioreactor UI. For dosing, LED, or temperature automations, hand off to the writing-automations skill instead.
---

# Build Pioreactor Jobs

## Overview

Build custom Pioreactor background jobs as plugin modules that can be discovered by `pio plugins list`, launched with `pio run <job_name>`, and optionally displayed in the Pioreactor UI.

## Workflow

1. First decide whether the request is a background job or an automation. If it is a dosing, LED, or temperature automation, use `$writing-automations`.
2. Inspect the current repo before editing: `core/pioreactor/background_jobs/base.py`, `core/pioreactor/cli/run.py`, the target plugin file if one exists, and similar examples in `plugins_dev/`.
3. Identify the development environment before choosing tests: repo-local development has pytest and no real hardware; on-device development has hardware and usually no repo test harness.
4. Confirm the environment root when it matters: local dev uses `TESTING=1` plus `PLUGINS_DEV`; devices use `/home/pioreactor/.pioreactor/plugins`; UI descriptors are rooted under `DOT_PIOREACTOR`.
5. Implement the job using the narrowest contrib base class:
   - Use `BackgroundJobContrib` for normal experiment-scoped plugin jobs.
   - Use `LongRunningBackgroundJobContrib` for jobs that run across experiments, usually with `UNIVERSAL_EXPERIMENT`.
   - Use `BackgroundJobWithDodgingContrib` only when the job must change behavior around OD readings.
6. Register a Click function named `click_<job_name>` so `pio run <job_name>` can discover it.
7. If the job should appear in the UI, add a YAML descriptor under `$DOT_PIOREACTOR/plugins/ui/jobs/`.
8. Validate discovery first, then runtime behavior.

## References

- Read `references/plugin-job-patterns.md` before creating or changing plugin job Python.
- Read `references/development-environments.md` before choosing where to create files or what validation to run.
- Read `references/ui-job-descriptors.md` before adding a job to the Pioreactor UI.
- Read `references/validation.md` before reporting the work complete.

## Rules

- Keep module-level work cheap and safe; plugin modules are imported during discovery.
- Avoid filenames that shadow standard library modules because the plugin directory is injected into `sys.path`.
- Keep `job_name`, Click command name, MQTT topics, config section names, and UI descriptor names aligned.
- Use `published_settings` for runtime-observable settings and `set_<setting>` methods when a settable value needs validation or side effects.
- Put cleanup in `on_disconnected`; cancel timers, close hardware handles, and leave hardware in a safe state.
- Prefer small targeted tests and smoke checks. Do not run the whole pytest suite for job work.
