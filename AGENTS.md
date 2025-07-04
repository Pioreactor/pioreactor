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
- Lint and check Python, bash, and SQL changes using `pre-commit run --files [FILES]`

## Tools

See the `makefile` for available tools.

## Logging

 All logs are added to `pioreactor.log`. You can tail the end with `make tail-logs`.

## Search and navigation

- The `CHANGELOG.md` has changes, and should be updated when appropriate (under the `Upcoming` section - add this section if not present.)
- **Always use `rg`** for searching and grepping instead of `grep` or `ls -R`. It is much faster and respects `.gitignore`.
- **Ignore** the `migration_scripts/`, `pioreactor/tests/data`, `update_scripts/` directories when searching.

## Important filesystem locations

- `.pioreactor/storage/` holds the main database, backups, and caches.
- `config.dev.ini` contains development configuration parameters.
- `.pioreactor/plugins/` is where Python plugin files (\*.py) can be added.
- `.pioreactor/experiment_profiles/` stores experiment profiles in YAML format.
- `.pioreactor/storage/calibrations/` stores calibration data.
