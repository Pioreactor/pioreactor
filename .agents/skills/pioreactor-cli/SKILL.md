---
name: pioreactor-cli
description: Use when running, debugging, documenting, or changing Pioreactor command-line workflows with `pio` or `pios`, including local job control, logs, MQTT, config, plugins, calibrations, worker targeting, config sync, cluster orchestration, and safe production command execution.
---

# Pioreactor CLI

## Purpose

Use this skill for Pioreactor CLI work involving:

- `pio`: local node commands for a leader, worker, or standalone Pioreactor.
- `pios`: leader-only commands that dispatch work to worker Pioreactors.

Prefer the command's current `--help` output and the implementation in `core/pioreactor/cli/` over remembered syntax.

## First Checks

1. Confirm the environment root when behavior depends on files, config, plugins, profiles, calibrations, databases, or logs:
   - `DOT_PIOREACTOR`
   - `GLOBAL_CONFIG`
   - `TESTING`
   - `PLUGINS_DEV`
   - `PIO_EXECUTABLE`
   - `PIOS_EXECUTABLE`
2. In this repo, prefer `.venv/bin/pio` and `.venv/bin/pios` over bare `pio` and `pios` unless the task is explicitly on-device.
3. For web-backed or Huey-backed commands, run `make dev-status` before starting services. Start only the services listed as missing.
4. Byte-cap unknown command output, for example:

```bash
.venv/bin/pio jobs running 2>&1 | head -c 4000
```

## Choosing `pio` vs `pios`

- Use `pio` for local unit work: start or stop one job, inspect logs, subscribe to MQTT, edit local config, manage local plugins, run calibrations, inspect jobs, or query the local database.
- Use `pios` from the leader for cluster work: run or kill jobs on multiple workers, update worker settings, sync configs, copy/remove files on workers, install/uninstall plugins, reboot/shutdown workers, or update app versions across units.
- Test a job or command locally with `pio` before scaling it through `pios` when that is practical.
- Remember that `pios` adds target selectors such as `--units` and `--experiments`; avoid relying on the default target set unless the user explicitly asked for all eligible workers.

## Safe Execution Rules

- Do not run broad production-affecting commands unless the user explicitly asked for that scope. Examples: `pios kill --all-jobs -y`, `pios shutdown`, `pios reboot`, `pios update app`, `pios rm`, and cluster-wide plugin changes.
- Prefer narrow targeting with `--units <unit>` or `--experiments <experiment>` for `pios` commands.
- For destructive or state-changing operations, first show or inspect the resolved target set when the CLI supports it, or use a safer read command such as `pio workers status`, `pio jobs running`, or the relevant `--help`.
- For commands that can block, stream indefinitely, or run jobs, use the harness background/session support when needed and make sure the process is stopped before finalizing.
- Never paper over failures by disabling tests or weakening command behavior. Diagnose whether the issue is code, environment, service state, or target reachability.

## Common Workflows

### Inspect Current CLI Syntax

```bash
pio --help
pio <command> --help
pios --help
pios <command> --help
```

### Local Job Work

```bash
pio jobs running
pio run <job_name> [job options]
pio update-settings <job_name> [setting options]
pio kill --job-name <job_name>
```

Check `core/pioreactor/background_jobs/base.py` and the job implementation when lifecycle, published settings, MQTT topics, or cleanup behavior matter.

### Cluster Job Work

```bash
pios run <job_name> --units <unit> [job options]
pios update-settings <job_name> --units <unit> [setting options]
pios kill --job-name <job_name> --units <unit>
```

For worker-targeted failures, distinguish leader dispatch failures from worker-local failures. Inspect the `pios` implementation, leader API route, Huey task, and worker `/unit_api` route as appropriate.

### Config and Plugin Work

- Local config edits or reads usually belong under `pio config` or direct config-file logic rooted at `DOT_PIOREACTOR`.
- Cluster config propagation belongs under `pios sync-configs`.
- Local plugin inspection belongs under `pio plugins`.
- Cluster plugin installs or removals belong under `pios plugins`, and should usually be targeted.

### Logs and MQTT

```bash
pio logs -n 50
pio mqtt -t "pioreactor/<unit>/<experiment>/<job_name>/#"
```

Use narrow MQTT topics when possible. Stop subscriptions before finalizing.

## Validation

- For CLI implementation changes, run the smallest relevant pytest target, usually a specific file or test under `core/tests/`.
- For command-syntax or discovery work, smoke check the current command:

```bash
pio <command> --help
pios <command> --help
```

- For live cluster behavior, report exactly what was run, which unit or experiment was targeted, and any services or environment variables that mattered.
