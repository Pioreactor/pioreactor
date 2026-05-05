# UI Descriptor Seed Assets

Built-in UI metadata copied to `~/.pioreactor/ui`.

Subdirectories:

- `jobs/`: built-in job/action descriptors shown in the UI.
- `settings/`: built-in passive setting collections shown in the UI.
- `automations/`: built-in automation descriptors grouped by automation family.
- `charts/`: built-in chart descriptors for overview pages.

These descriptors are seed files. Plugins and user customizations can add additional descriptors under `~/.pioreactor/plugins/ui`.

`ui/settings/00_bioreactor.yaml` controls presentation of canonical bioreactor variables. It can hide, show, label, and order fields, but it does not define new bioreactor variables. New bioreactor variables must be added in core first, then exposed through the descriptor.
