**web directory summary**

`$experiment` (`UNIVERSAL_EXPERIMENT`) is an intentional virtual experiment for self-tests and system activity, not a missing user-created experiment. Telemetry, logs, and historical-worker queries may contain it without an `experiments` row. Keep named-experiment metadata/edit validation separate from these paths. Preserve virtual rows when joining optional experiment metadata; elapsed time is undefined without a start time. The MQTT writer deliberately permits these records, although `PRAGMA foreign_key_check` may report them. See the root `AGENTS.md` database guidance before changing enforcement or migration checks.

This project is a Flask-based backend for the Pioreactor UI. The codebase exposes two main sets of REST endpoints: one for the leader node (`/api`) and one for individual workers (`/unit_api`). MQTT is used for logging and coordination, while Huey handles asynchronous tasks such as executing `pio` commands or propagating updates.

Key modules:

*   **`app.py`** – Initializes the Flask app, configures logging, loads plugins, provides helper DB functions, and registers `unit_api` on every unit plus `api` and `mcp` when running on the leader.

*   **`api.py`** – Contains over 100 routes for cluster‑wide operations: starting/stopping jobs, synchronizing configs, retrieving logs, exporting datasets, managing experiments, etc. Routes use Huey tasks to broadcast commands across workers.

*   **`unit_api.py`** – Worker‑level API with endpoints to run jobs, update or reboot a unit, handle calibrations, inspect filesystem paths, and manage running job settings.

*   **`fanout.py`** – Owns the leader-side broadcast helpers that fan out `/api` requests across cluster units or workers via the underlying Huey multicast tasks.

*   **`tasks.py`** – Defines Huey tasks that wrap command‑line tools (`pio`, `pios`) and also provide helper tasks for HTTP calls to workers. Tasks manage updates, clock synchronization, plugin installation, etc. Example functions include `pio_run`, `pio_update_app`, and raw cluster multicast helpers.

*   **`cache.py`** – Owns the leader-side fan-out cache for worker `/unit_api` reads, including cache target definitions, invalidation helpers, and the cached multicast read implementation.

*   **`utils.py`** – Helper utilities for caching responses, rate limiting, validating filenames, and validating request payloads with msgspec structs.

*   **`API_CONVENTIONS.md`** – Canonical HTTP method semantics and the compatibility policy for older method aliases.


The repository also includes generated frontend build output in the `static/` directory and startup scripts (`fcgi.py`). Treat `static/` as generated output; do not inspect or edit it during normal code search.

Overall, the project provides a REST API and task queue framework to manage Pioreactor clusters, interact with hardware via CLI commands, and expose data/logs to a web UI.
