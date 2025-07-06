# Agent Guidelines for the mono-repo

This project contains the executable code for the Pioreactor project. There are three important sub-projects:

1. `pioreactor/`: this project is the backend / worker code that handles the running jobs.
2. `web/`: this project is our web API
3. `frontend/`: this project contains React code for our web UI frontend.


## Running

The following is a good startup order:

1. Start the Huey process with `make huey-dev`
2. Start the web-api with `make web-dev` (port 4999)
3. Start the React server with `make frontend-dev` (port 3000)
4. (optional) Run pioreactor jobs with `pio run XYZ` (example).

## Edits

Don't make unnecessary formatting changes to the files you edit. We have a linter that can do that.

If you need to write some custom code or tools, you can do so in the `scratch/` folder.

Don't bother linting or running `pre-commit`.


## Tools

See the `makefile` for available tools.

### Important commands

```
make tail-log       ## show last 10 lines of the merged pioreactor log (override with, ex, LINES=200)
make huey-dev       ## Run the Huey consumer with sensible dev flags
make frontend-dev   ## Run React dev server on :3000
make web-dev        ## Run Flask API on 127.0.0.1:4999
```

## Logging

 All logs are added to `pioreactor.log`. You can tail the end with `make tail-logs`.

## Search and navigation

- **Always use `rg`** for searching and grepping instead of `grep` or `ls -R`. It is much faster and respects `.gitignore`.
- **Ignore** the `migration_scripts/`, `pioreactor/tests/data`, `update_scripts/` directories when searching.
