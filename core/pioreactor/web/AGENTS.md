**web directory summary**

This project is a Flask-based backend for the Pioreactor UI. The codebase exposes two main sets of REST endpoints: one for the leader node (`/api`) and one for individual workers (`/unit_api`). MQTT is used for logging and coordination, while Huey handles asynchronous tasks such as executing `pio` commands or propagating updates.

Key modules:

*   **`app.py`** – Initializes the Flask app, configures logging, loads plugins, provides helper DB functions, and registers `unit_api` on every unit plus `api` and `mcp` when running on the leader.

*   **`api.py`** – Contains over 100 routes for cluster‑wide operations: starting/stopping jobs, synchronizing configs, retrieving logs, exporting datasets, managing experiments, etc. Routes use Huey tasks to broadcast commands across workers.

*   **`unit_api.py`** – Worker‑level API with endpoints to run jobs, update or reboot a unit, handle calibrations, inspect filesystem paths, and manage running job settings.

*   **`fanout.py`** – Owns the leader-side broadcast helpers that fan out `/api` requests across cluster units or workers via the underlying Huey multicast tasks.

*   **`tasks.py`** – Defines Huey tasks that wrap command‑line tools (`pio`, `pios`) and also provide helper tasks for HTTP calls to workers. Tasks manage updates, clock synchronization, plugin installation, etc. Example functions include `pio_run`, `pio_update_app`, and raw cluster multicast helpers.

*   **`cache.py`** – Owns the leader-side fan-out cache for worker `/unit_api` reads, including cache target definitions, invalidation helpers, and the cached multicast read implementation.

*   **`utils.py`** – Helper utilities for caching responses, rate limiting, validating filenames, and validating request payloads with msgspec structs.


The repository also includes generated frontend build output in the `static/` directory and startup scripts (`fcgi.py`). Treat `static/` as generated output; do not inspect or edit it during normal code search.

Overall, the project provides a REST API and task queue framework to manage Pioreactor clusters, interact with hardware via CLI commands, and expose data/logs to a web UI.
