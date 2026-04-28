# Agent Guidelines for the Pioreactor Mono-Repo

This repository contains the **executable code for the Pioreactor project**. It has three primary sub-projects:

1. `core/` — backend / worker code that runs jobs. Important files:
   - `core/pioreactor/background_jobs/base.py` is the super class for background jobs (like stirring, od_reading, automations, etc)
2. `core/pioreactor/web/` — Flask-based web API. Important files:
   - `core/pioreactor/web/api.py` handles the leader-only (and frontend) API. This is the main entry point most often. It sends requests to `unit_api.py` too.
   - `core/pioreactor/web/unit_api.py` is the pioreactor-specific API for controlling individual actions on a Pioreactor.
   - `core/pioreactor/web/tasks.py` lists the Huey (background) tasks spawned by the web APIs.
3. `frontend/` — React-based web UI

---

## Key components

* **Background Jobs**
  Long-running tasks inherit from `BackgroundJob` in `core/pioreactor/background_jobs/base.py`. Examples include stirring control (`stirring.py`), optical density readings (`od_reading.py`), temperature automation, dosing automation.

* **Automations**
  Higher-level automation logic derives from `AutomationJob` in `core/pioreactor/automations/base.py`. Dosing, temperature, and LED automations are implemented under `core/pioreactor/automations/`.

* **Command-Line Interface**
  The `pio` CLI in `core/pioreactor/cli/pio.py` provides commands to run jobs, adjust settings, view logs, and update software. It checks for first-boot success and ensures the user is not running as root.

* **Configuration System**
  Configuration is loaded through `get_config()` in `core/pioreactor/config.py`, which merges global and unit-specific files and creates additional sections like `PWM_reverse`. A sample development config is provided in `config.dev.ini` with settings for PWM channels, stirring parameters, OD reading, MQTT broker, UI options, and more.

* **Hardware Utilities**
  `core/pioreactor/hardware.py` defines GPIO pin mappings and I2C addresses depending on hardware version. Modules in `core/pioreactor/utils/` implement PWM control, ADC/DAC access, temperature sensors, and network helpers.

* **Data Structures and Messaging**
  Typed message structures for MQTT communication—such as `ODReadings`, `DosingEvent`, and `CalibrationBase`—are defined in `core/pioreactor/structs.py`.

* **Version and Device Info**
  Software version and hardware detection logic reside in `core/pioreactor/version.py`, exposing `__version__` and helper functions like `get_hardware_version()`.

* **Plugin System**
  Additional functionality can be loaded via Python entry points or drop-in `.py` files under `~/.pioreactor/plugins`. Plugins are discovered and registered in `core/pioreactor/plugin_management/__init__.py`.

* **Web API and UI**
  The `core/pioreactor/web/` directory includes our APIs and built frontend React projects.

---

## Running the system

ALWAYS use the project virtualenv for any Python, mypy, or pytest commands.

```bash
.venv/bin/
```

We use Python 3.13.

## Environment model

This repo's local development behavior depends heavily on environment variables. Many bugs that look like code regressions are actually the process reading from the wrong environment root or using the wrong interpreter.

Common variables you should assume are meaningful:

- `TESTING=1`
- `GLOBAL_CONFIG`
- `DOT_PIOREACTOR`
- `RUN_PIOREACTOR`
- `PLUGINS_DEV`
- `PIO_EXECUTABLE`
- `PIOS_EXECUTABLE`

These are likely defined in the local `.envrc` file.

Do not assume bare `python`, `pytest`, or `mypy` point at the correct interpreter. Prefer `.venv/bin/python`, `.venv/bin/pytest`, and `.venv/bin/mypy`.

`DOT_PIOREACTOR` is the effective data root for much of the application. When debugging filesystem, calibration, profile, plugin, backup/restore, or config issues, confirm which `DOT_PIOREACTOR` root the process is using before changing code.

**Startup order (recommended):**

0. Before starting anything, run `make dev-status` to see whether the Huey consumer, Flask API (4999), or frontend dev server (3000) are already up. Only launch what's listed under "Need to start".
1. Start the Huey consumer:

   ```bash
   make huey-dev
   ```
2. Start the web API (port **4999**):

   ```bash
   make web-dev
   ```
3. Start the React dev server (port **3000**):

   ```bash
   make frontend-dev
   ```
4. (Optional) Run Pioreactor jobs, e.g.:

   ```bash
   pio run XYZ
   pio kill --job-name XYZ
   ```

   Some jobs might be blocking and long-running, so use the background feature of your harness to not block.

---

## Tools & commands

Available commands are listed in the `Makefile`. Key ones:

```bash
make dev-status    # Summarizes which dev servers are already running vs need to be started
make huey-dev      # Run Huey consumer with dev flags
make web-dev       # Run Flask API on 127.0.0.1:4999
make frontend-dev  # Run React dev server on 127.0.0.1:3000
```

`make dev-status` either reports "All dev services appear to be running" with brief details, or prints a "Need to start" list with only the missing services. Start only those listed; everything else is already running.

---

## Decision-making

- If a non-trivial code change has 2–3 valid approaches, ask the user first before editing.

---

## Testing

 - Use **pytest** for Python tests. All tests take in excess of 30 minutes, so don't run the entire test suite. Instead run specific files or tests using pytest options.

  ```bash
  .venv/bin/pytest core/tests/test_cli.py
  ```
 - Don't run tests in parallel.
 - Skipping tests is okay, but note it to the user.
 - Disabling tests is okay, however you MUST ASK PERMISSION to **disable** a test only if any of the following:
    - it is incredibly flakey and unreliable.
    - relies on an unresponsive external service.
 - Deleting tests is okay, however you MUST ASK PERMISSION to **delete** a test only if:
    - its conclusion is orthogonal to the logic being written.
    - its preventing a better refactor or feature.
    - its an incredibly trivial feature that is unlikely to be used.
 - Keep mypy green:

  ```bash
  .venv/bin/mypy core/pioreactor --ignore-missing-imports
  ```
---

## Logging

* All logs are written to **`pioreactor.log`**.
* To view recent logs:

  ```bash
  pio logs -n 10
  ```

---

## MQTT

We make use a mosquitto MQTT. Try `pio mqtt` to get a feed, or subset with `pio mqtt -t "your topic"`.

---

## Search & navigation

When searching the repo, exclude these directories:

* `core/tests/data/`
* `core/update_scripts/`
* `core/tests/data`
* `core/experiments/`

Also exclude  `CHANGELOG.md` files.

---

## CI

We run GitHub Actions for CI, located in `.github/workflows/ci.yaml`.

---

## Important filesystem locations

- `.pioreactor/config.ini` contains development configuration parameters.
- `.pioreactor/plugins/` is where Python plugin files (`*.py`) can be added.
- `.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.
- `.pioreactor/storage/` holds the main database, backups, and caches.
- `.pioreactor/storage/calibrations/` stores calibration data.
- `.pioreactor/storage/estimators/` stores estimator data.

Many of the paths above are resolved in practice from `DOT_PIOREACTOR`, not from the git checkout layout. Expect config files, calibrations, experiment profiles, models, exportable datasets, and many plugin/UI extension paths to be rooted there.

---

## Web architecture: where fixes usually belong

For web and cluster-control changes, decide which ownership boundary is correct before editing:

- `core/pioreactor/web/api.py` owns leader-facing routes, cluster orchestration, and most frontend-facing endpoints.
- `core/pioreactor/web/unit_api.py` owns per-unit routes and unit-local mutations, including many filesystem and calibration operations.
- `core/pioreactor/web/tasks.py` owns Huey tasks, async execution, and wrappers around `pio` / `pios` commands.
- `core/pioreactor/web/fanout.py` owns leader-side broadcast helpers across workers.
- `core/pioreactor/web/cache.py` owns short-TTL leader-side caching for fan-out reads.

A common mistake is patching `api.py` when the real behavior belongs in `unit_api.py` or in the Huey task layer.

Some leader `/api` read endpoints fan out to worker `/unit_api` routes and may use a short-TTL leader-side cache. When adding or changing cluster-wide reads:

- prefer existing cached fan-out helpers when the response can tolerate brief staleness
- keep cached payloads close to the uncached worker payload shape
- add explicit invalidation on successful writes
- avoid caching highly volatile or write-heavy paths

---

## Calibration subsystem

Calibrations are a first-class subsystem, not just YAML files on disk.

Important files and areas:

- `core/pioreactor/calibrations/structured_session.py`
- `core/pioreactor/calibrations/session_flow.py`
- `core/pioreactor/web/unit_calibration_sessions_api.py`
- related calibration tests under `core/tests/` and `core/tests/web/`

Calibration changes often span several layers at once:

- storage format and YAML serialization
- protocol registration
- session-flow and step-transition logic
- CLI behavior
- unit API endpoints
- frontend dialogs and charts

When editing calibration behavior, expect to verify both backend tests and the UI/API contract.

---

## Plugin development

In local development, plugin behavior may come from `PLUGINS_DEV` rather than only from installed plugins under `~/.pioreactor/plugins`.

When working on plugins:

- confirm whether the environment is running with `TESTING=1`
- verify which plugin directory is actually being scanned
- remember plugins may register background jobs, automations, API routes, and UI extensions

---

## Database schema

Get the latest database schema:

```
curl -fsSL https://raw.githubusercontent.com/Pioreactor/CustoPiZer/refs/heads/pioreactor/workspace/scripts/files/sql/create_tables.sql
```


## Business logic

Make sure to consider the following when editing and reviewing code.

- One of the Raspberry Pi's is assigned as the "leader", and this hosts most of the services: web server, MQTT broker, database, etc. It also sends commands to any "workers". The leader can also be a worker. Together, the leader and all the workers are called a "cluster". A cluster can be a small as a single leader+worker. Pioreactors are assigned to be a leader, worker, or both based on the custom image they install.
- Different jobs, like stirring, OD reading, dosing, etc. are controlled by separate Python objects. Some jobs will passively listen for events from other jobs, and change their behavior in response, for example, dosing automations listen to OD readings, and may respond by dosing or not dosing.
- The main "control plane" for the Pioreactor software is the command line interface, pio. For example, when the user starts a activity from the UI, the web server will run `pio run X ...`, which launches a Python process that will instantiate the object the controls the activity.
- Because each activity is a separate Python process, we can modify an activity before running it by changing files on the filesystem.
- The Raspberry Pis / Pioreactors communicate through the local network (in more advanced cases, this network is hosted on the leader). Users control the Pioreactor cluster while being on the same network, and accessing the web UI or the command line of the Pioreactors.
- Leaders talk to Pioreactors via HTTP requests between their respective web servers (using lighttpd + Flask, on port 80 by default). Workers send experiment data back to the leader via MQTT (see below). We expect users to control the leader only (using the web interface or CLI), and let the leader control the workers (there are exceptions).
- The Pioreactor UI also connects to MQTT, and uses it to push and pull live data from the activities in each Pioreactor (states of activities, settings, graphs, etc).

---

## Purpose and usage

The Pioreactor software enables users to control and monitor small-scale bioreactors. It supports features such as:

* Running stirring, optical density measurement, and dosing automatically.
* Managing a cluster of Pioreactors via MQTT and HTTP APIs.
* Applying calibrations for pumps, stirring, and OD readings.
* Scheduling complex experiment profiles that coordinate multiple jobs across workers.

## Tickets

Tickets looks like `pio-xxxx`. Not sure what to do? Try looks through open tickets.
