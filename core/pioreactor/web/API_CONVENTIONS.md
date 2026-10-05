# HTTP API conventions

Pioreactor's leader `/api` and per-unit `/unit_api` routes use HTTP methods
consistently so clients can infer how to call a new endpoint from its
semantics.

- `POST` starts a command or creates an asynchronous task.
- `PATCH` partially updates an existing resource.
- `PUT` replaces a resource idempotently.
- `DELETE` removes a resource.

Some command and replacement routes still accept older methods for backwards
compatibility. New Pioreactor clients should use the canonical method above.
Compatibility aliases should remain covered by route-contract tests until an
explicit deprecation and removal plan is published.

## Intended worker identity

Leader-to-unit HTTP mutations send `X-Pioreactor-Target: <unit hostname>`.
Before running a POST, PATCH, PUT, or DELETE handler, `/unit_api` checks this
header against its own hostname. A different or empty target returns HTTP 409
with no handler side effects or queued work. Broadcasts send each destination's
individual hostname, never `$broadcast`.

The header is optional for direct API clients: requests without it retain their
existing behavior. Read requests are unchanged. This guards accidental address
reuse, not authentication, and assumes workers run a version supporting the
check; older workers may ignore the header.

Covered callers include Huey fanout, direct leader API proxies (including
unit-specific config, calibration sessions, camera files, and archive imports),
USB plugin installation HTTP commands, `pios` HTTP commands, cluster job stops,
and experiment-profile starts/stops. An HTTP 409 from `pios update app` must not
trigger its SSH fallback.

The frontend also supplies the configured leader hostname for direct, leader-local
`/unit_api` mutations: USB mount/eject, profile start/stop, long-running job and
web-server restarts, and system archive import. It does not send these mutations
until the target hostname is available; read requests remain unchanged.

SSH and rsync operations are outside this HTTP contract, including shared-config
sync, `pios cp`, and staging USB plugin files before installation. They need a
separate destination guard. Inventory cleanup uses
`POST /unit_api/system/cleanup_after_inventory_removal` with the same optional header;
it only stops worker jobs and removes shared config. The leader's
`DELETE /api/workers/<unit>` owns deletion of the inventory database record.
