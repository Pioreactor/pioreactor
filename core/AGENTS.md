# Agent Guidelines for pioreactor backend project

This document provides guidelines and useful information for AI agents contributing to the Pioreactor codebase.

## Edits

Don't make unnecessary formatting changes to the files you edit. We have a linter that can do that.

## Running

- We use Python 3.11.
- The Pioreactor CLI is invoked via `pio`. For example:
  ```bash
  pio run stirring
  ```
  Some `pio` commands are long running and require an explicit interrupt to end them.

## Testing and linting.

- **Use `pytest`** to run tests.
- Don't run the entire test suite unless requested (that is, don't run `pytest core`. Instead, either use the `-k` command to run specific tests you think are relevant, or run an entire file.
- Don't bother linting or running `pre-commit`.

## Tools

See the `makefile` for available tools.

### Important commands

```
make tail-log       ## show last 10 lines of the merged pioreactor log (override with, ex, LINES=200)
make tail-mqtt      ## Tail mosquitto
```

## Logging

 All logs are added to `../pioreactor.log`. You can tail the end with `make tail-logs`.

## Search and navigation

- **Ignore** the `migration_scripts/`, `tests/data`, `update_scripts/`, `experiments/`, `jupyer_notebooks/` and `CHANGELOG.md` directories when searching.

## Important filesystem locations

- `../.pioreactor/storage/` holds the main database, backups, and caches.
- `../.pioreactor/config.ini` contains development configuration parameters.
- `../.pioreactor/plugins/` is where Python plugin files (\*.py) can be added.
- `../.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.
- `../.pioreactor/storage/calibrations/` stores calibration data.


**Directory Summary**

This repository contains the open‑source control software for the Pioreactor—a Raspberry‑Pi–based bioreactor platform. The project uses Python 3.11 and relies heavily on MQTT for communication between processes. Core functionality is organized into “background jobs” that manage hardware components such as pumps, stirrers, temperature sensors, and LEDs.

**Key Components**

*   **Background Jobs**
    Long‑running tasks inherit from `BackgroundJob` in `pioreactor/background_jobs/base.py`. Examples include stirring control (`stirring.py`), optical density readings (`od_reading.py`), temperature automation, dosing automation, and worker message summarization via Codex (`codex_summary.py`).

*   **Automations**
    Higher‑level automation logic derives from `AutomationJob` in `pioreactor/automations/base.py`. Dosing, temperature, and LED automations are implemented under `pioreactor/automations/`.

*   **Command‑Line Interface**
    The `pio` CLI in `pioreactor/cli/pio.py` provides commands to run jobs, adjust settings, view logs, and update software. It checks for first‑boot success and ensures the user is not running as root.

*   **Configuration System**
    Configuration is loaded through `get_config()` in `pioreactor/config.py`, which merges global and unit‑specific files and creates additional sections like `PWM_reverse`. A sample development config is provided in `config.dev.ini` with settings for PWM channels, stirring parameters, OD reading, MQTT broker, UI options, and more.

*   **Hardware Utilities**
    `pioreactor/hardware.py` defines GPIO pin mappings and I2C addresses depending on hardware version. Modules in `pioreactor/utils/` implement PWM control, ADC/DAC access, temperature sensors, and network helpers.

*   **Data Structures and Messaging**
    Typed message structures for MQTT communication—such as `ODReadings`, `DosingEvent`, and `CalibrationBase`—are defined in `pioreactor/structs.py`.

*   **Version and Device Info**
    Software version and hardware detection logic reside in `pioreactor/version.py`, exposing `__version__` and helper functions like `get_hardware_version()`.

*   **Plugin System**
    Additional functionality can be loaded via Python entry points or drop‑in `.py` files under `~/.pioreactor/plugins`. Plugins are discovered and registered in `pioreactor/plugin_management/__init__.py`.

*   **Testing**
    The `tests/` directory includes pytest-based unit tests and fixtures for simulating hardware interactions.


*   **Web API and UI**
    The `pioreactor/web/` directory includes our APIs and built frontend React projects.



**Purpose and Usage**

The Pioreactor software enables users to control and monitor small-scale bioreactors. It supports features such as:

*   Running stirring, optical density measurement, and dosing automatically.

*   Managing a cluster of Pioreactors via MQTT and HTTP APIs.

*   Applying calibrations for pumps, stirring, and OD readings.

*   Scheduling complex experiment profiles that coordinate multiple jobs across workers.
