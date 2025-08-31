**web directory summary**

This project is a Flask-based backend for the Pioreactor UI. The codebase exposes two main sets of REST endpoints: one for the leader node (`/api`) and one for individual workers (`/unit_api`). MQTT is used for logging and coordination, while Huey handles asynchronous tasks such as executing `pio` commands or propagating updates.

Key modules:

*   **`__init__.py`** – Initializes the Flask app, sets up MQTT, configures logging, and provides helper DB functions. It loads plugins and registers the blueprints for `api` and `unit_api` when running on the leader. Example lines show MQTT setup and app creation.

*   **`api.py`** – Contains over 100 routes for cluster‑wide operations: starting/stopping jobs, synchronizing configs, retrieving logs, exporting datasets, managing experiments, etc. Routes use Huey tasks to broadcast commands across workers.

*   **`unit_api.py`** – Worker‑level API with endpoints to run jobs, update or reboot a unit, handle calibrations, inspect filesystem paths, and manage running job settings.

*   **`tasks.py`** – Defines Huey tasks that wrap command‑line tools (`pio`, `pios`) and also provide helper tasks for HTTP calls to workers. Tasks manage updates, clock synchronization, plugin installation, etc. Example functions include `pio_run`, `pio_update_app`, and cluster multicast helpers.

*   **`structs.py`** – Msgspec `Struct` definitions for validating request payloads, such as job options or automation descriptors.

*   **`utils.py`** – Helper utilities for caching responses, rate limiting, and validating filenames.

*   **`contrib/`** – YAML descriptors for default charts, background jobs, and automation templates. These files let users extend the UI by defining new automations and charts.



The repository also includes a compiled frontend in the `static/` directory and startup scripts (`fcgi.py`).

Overall, the project provides a REST API and task queue framework to manage Pioreactor clusters, interact with hardware via CLI commands, and expose data/logs to a web UI.
