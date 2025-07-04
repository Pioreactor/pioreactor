# Agent Guidelines

This document provides guidelines and useful information for AI agents contributing to the Pioreactor codebase.

## Edits

Don't make unnecessary formatting changes to the files you edit. We have a linter that can do that.

## Running

- We use Python 3.11.
- The Pioreactor CLI is invoked via `pio`. For example:
  ```bash
  pio run stirring
  ```
  Some `pio` commands are long running and require an interrupt to end them.

## Testing

- **Use `python3 -m pytest`** to run tests. Don't run the entire test quite unless requested. Using the `-k` command to run specific tests you think are relevant.
- Lint and check changes using `pre-commit run`

## Search and navigation

- The `CHANGELOG.md` has changes, and should be updated when appropriate (under the `Upcoming` section - add this section if not present.)
- **Always use `rg`** for searching and grepping instead of `grep` or `ls -R`. It is much faster and respects `.gitignore`.
- **Ignore** the `migration_scripts/` and `update_scripts/` directories when searching.

## Important filesystem locations

Below is a list of important filesystem locations and files in the Pioreactor project:

### Storage

- `.pioreactor/storage/` holds the main database, backups, and caches.

### Configuration

- `config.dev.ini` contains development configuration parameters.

### Plugins

- `.pioreactor/plugins/` is where Python plugin files can be added.

### Experiment profiles

- `.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.

### Calibrations

- `.pioreactor/storage/calibrations/` stores calibration data.
