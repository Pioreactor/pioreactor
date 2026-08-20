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
