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

- **Use `python3 -m pytest`** to run tests. Don't run the entire test quite unless requested. Using the `-k` command to run specific tests you think are relevant.
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

- The `CHANGELOG.md` has changes, and should be updated when appropriate (under the `Upcoming` section - add this section if not present.)
- **Ignore** the `migration_scripts/`, `pioreactor/tests/data`, `update_scripts/`, `experiments/`, `jupyer_notebooks/` directories when searching.

## Important filesystem locations

- `../.pioreactor/storage/` holds the main database, backups, and caches.
- `../.pioreactor/config.ini` contains development configuration parameters.
- `../.pioreactor/plugins/` is where Python plugin files (\*.py) can be added.
- `../.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.
- `../.pioreactor/storage/calibrations/` stores calibration data.
