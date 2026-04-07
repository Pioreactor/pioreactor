**web directory summary**

This project is a Flask-based backend for the Pioreactor UI. The codebase exposes two main sets of REST endpoints: one for the leader node (`/api`) and one for individual workers (`/unit_api`). MQTT is used for logging and coordination, while Huey handles asynchronous tasks such as executing `pio` commands or propagating updates.

Key modules:

*   **`__init__.py`** – Initializes the Flask app, sets up MQTT, configures logging, and provides helper DB functions. It loads plugins and registers the blueprints for `api` and `unit_api` when running on the leader. Example lines show MQTT setup and app creation.

*   **`api.py`** – Contains over 100 routes for cluster‑wide operations: starting/stopping jobs, synchronizing configs, retrieving logs, exporting datasets, managing experiments, etc. Routes use Huey tasks to broadcast commands across workers.

*   **`unit_api.py`** – Worker‑level API with endpoints to run jobs, update or reboot a unit, handle calibrations, inspect filesystem paths, and manage running job settings.

*   **`fanout.py`** – Owns the leader-side broadcast helpers that fan out `/api` requests across cluster units or workers via the underlying Huey multicast tasks.

*   **`tasks.py`** – Defines Huey tasks that wrap command‑line tools (`pio`, `pios`) and also provide helper tasks for HTTP calls to workers. Tasks manage updates, clock synchronization, plugin installation, etc. Example functions include `pio_run`, `pio_update_app`, and raw cluster multicast helpers.

*   **`cache.py`** – Owns the leader-side fan-out cache for worker `/unit_api` reads, including cache target definitions, invalidation helpers, and the cached multicast read implementation.

*   **`structs.py`** – Msgspec `Struct` definitions for validating request payloads, such as job options or automation descriptors.

*   **`utils.py`** – Helper utilities for caching responses, rate limiting, and validating filenames.


The repository also includes a compiled frontend in the `static/` directory and startup scripts (`fcgi.py`).

Overall, the project provides a REST API and task queue framework to manage Pioreactor clusters, interact with hardware via CLI commands, and expose data/logs to a web UI.


**leader fan-out cache**

Some leader `/api` endpoints fetch read-only data from many workers by calling worker `/unit_api` routes. For these paths, we now support a leader-side cache that stores per-worker responses for a short TTL and reuses them on repeated reads.

Current implementation details:

*   The cache lives in `local_intermittent_storage`, not `local_persistent_storage`.
*   The storage namespace is `leader_multicast_get_cache`, defined by `LEADER_MULTICAST_GET_CACHE` in `cache.py`.
*   In the sqlite cache layer, the table name becomes `cache_leader_multicast_get_cache`.
*   Cache entries are keyed by a tuple:
    *   `("multicast_get", cache_namespace, endpoint, unit)`
*   Values are msgspec-json encoded objects of the form:
    *   `{"cached_at": <unix-seconds>, "value": <worker-response-payload>}`
*   TTL is enforced on read in `_read_multicast_get_cache_entry(...)` in `cache.py`.
*   The low-level cache implementation lives in `cache.multicast_get_with_leader_cache(...)`, and the Huey task wrapper remains in `tasks.py`.
*   In `api.py`, leader routes should usually go through `cache.cached_multicast_get(...)` instead of calling the task helper directly.
*   The TTL value itself is set by callers of `multicast_get_with_leader_cache(...)`. The current helper uses the default `ttl_s=10.0`.


**how to use it**

Use the leader cache when all of the following are true:

*   The endpoint is a leader-side fan-out read over worker `/unit_api` routes.
*   The payload is safe to be stale for a few seconds.
*   The response is expensive enough that repeated reads matter.
*   You can clearly identify the write paths that should invalidate it.

Do not use this pattern for:

*   write operations
*   long-running jobs where the task result itself is the point
*   highly volatile state that users expect to be fresh on every request


**how to add a new cached object**

If you want to cache another fan-out object, such as estimators or plugins, follow this pattern:

1. Define a `MulticastGetCacheTarget` in `cache.py`.
   *   Example: `ESTIMATORS = MulticastGetCacheTarget("estimators", "/unit_api/estimators")`
2. Change the leader read route to use `cache.cached_multicast_get(...)` instead of `tasks.multicast_get(...)`.
   *   Example: `cache.cached_multicast_get(cache.ESTIMATORS, get_all_workers())`
3. Add an invalidation helper in `cache.py` for that object family.
   *   Mirror `invalidate_calibrations_cache(...)` or `invalidate_estimators_cache(...)`.
4. Call that invalidation helper from every successful mutation route that changes the cached payload.
   *   For a single unit, invalidate only that unit.
   *   For `$broadcast`, invalidate all workers covered by the route.
5. Inside invalidation helpers, use `invalidate_multicast_get_cache(...)` with one or more cache targets.
   *   Example: `invalidate_multicast_get_cache([ESTIMATORS, ACTIVE_ESTIMATORS], units)`
6. Add focused tests:
   *   cache hit avoids the uncached fetch path
   *   route uses the cached helper
   *   mutation invalidates the right unit keys


**example: calibrations**

Calibrations are the first slice using this pattern:

*   Cache target in `cache.py`: `CALIBRATIONS = MulticastGetCacheTarget("calibrations", "/unit_api/calibrations")`
*   Cached route: `/api/workers/<pioreactor_unit>/calibrations`
*   Invalidation happens before these calibration mutations are queued:
    *   create calibration
    *   delete calibration
    *   set active calibration
    *   clear active calibration

Related calibration targets now include:

*   `CALIBRATIONS`
*   `ACTIVE_CALIBRATIONS`
*   `CALIBRATION_PROTOCOLS`

That means repeated visits to the calibration listing can avoid worker fan-out and YAML parsing on warm reads, while writes still clear the affected cached entries.


**practical notes**

*   Prefer per-worker cached payloads over one giant broadcast blob. Per-worker keys make invalidation much cheaper and are reusable for both single-unit and broadcast routes.
*   Keep TTL short unless you have strong invalidation and a clear product reason for longer staleness.
*   Do not cache failures for long. The current implementation skips writing `None` results into the cache.
*   Keep the cached value shape identical to the uncached worker payload unless there is a strong reason not to. It makes reuse and debugging much easier.
