# Agent Guidelines

This document provides guidelines and useful information for AI agents contributing to the Pioreactor codebase.

## Running

- **Use `pytest`** to run tests.
- We use Python 3.11.
- The Pioreactor CLI is invoked via `pio`. For example:
  ```bash
  pio run stirring
  ```
  Some `pio` commands are available without a webserver running (hosted on the "leader"); these can be ignored.

## Search and navigation

- The `CHANGELOG.md` has changes, and should be updated when appropriate (under the `Upcoming` section, if available.)
- **Always use `rg`** for searching and grepping instead of `grep` or `ls -R`. It is much faster and respects `.gitignore`.
- **Ignore** the `migration_scripts/` and `update_scripts/` directories when searching.

## Important filesystem locations

Below is a list of important filesystem locations and files in the Pioreactor project:

### Storage

- `.pioreactor/storage/` holds the main database, backups, and persistent caches.
- `/tmp/pioreactor_cache/` holds temporary caches (cleared between reboots).

### Configuration

- `config.dev.ini` contains development configuration parameters.

### Plugins

- `.pioreactor/plugins/` is where Python plugin files can be added.

### Experiment profiles

- `.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.

### Calibrations

- `.pioreactor/storage/calibrations/` stores calibration data.
