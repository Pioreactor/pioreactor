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
reuse, not authentication.

Covered callers include Huey fanout, direct leader API proxies (including
unit-specific config, calibration sessions, camera files, and archive imports),
USB plugin installation HTTP commands, `pios` HTTP commands, cluster job stops,
and experiment-profile starts/stops. An HTTP 409 from `pios update app` must not
trigger its SSH fallback.

The frontend does not send the header. Its `/unit_api` requests are same-origin,
so they always reach the unit that served the page.

SSH and rsync operations are outside this HTTP contract, including shared-config
sync, `pios cp`, and staging USB plugin files before installation. They need a
separate destination guard. Inventory cleanup uses
`POST /unit_api/cluster/leave` with the same optional header;
the worker undoes its join (stops jobs, removes shared config and its chrony source) and reboots. The leader's
`DELETE /api/workers/<unit>` owns deletion of the inventory database record.

## Fanout failures and safe retries

`retryable` means it is safe to repeat the original request. A missing response,
HTTP 5xx, or unreadable response to a mutation does not establish that the
mutation failed before execution. These ambiguous failures return
`retryable: false`, `outcome: "unknown"`, and `recovery_action: "check_state"`.
Inspect unit state before deciding what to do next; do not automatically resubmit
the mutation. Generic fanout task exceptions and missing results are also
conservative because they do not establish whether execution occurred.

If a worker already accepted a task, interrupted polling returns
`retryable: false`, `outcome: "unknown"`, and `recovery_action: "poll_task"`.
The `operation` object retains `unit`, `task_id` (when supplied), and
`result_url_path`. That path is relative to the **worker**, not the leader:
GET it on `operation.unit`. For registered workers, clients can alternatively
GET `/api/workers/<unit>/task_results/<task_id>` on the leader.
Repeat these read requests to observe the existing operation; do not repeat the
original mutation. A polling failure does not cancel the worker task.

Transient failures of initial GET requests remain retryable. No idempotency-key
or command-deduplication guarantee is provided by this contract.
