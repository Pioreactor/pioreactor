# Development Environments

Use this reference before choosing paths, test commands, or verification strategy. Plugin job development looks different depending on where the agent is running.

## Repo-local development

This is the usual laptop or workstation setup:

- The user has cloned the Pioreactor repo.
- The project virtualenv and test tools are available.
- Local plugin modules usually live in `plugins_dev/`.
- Discovery depends on `TESTING=1` and `PLUGINS_DEV`.
- The agent can run repo tests, import checks, mypy, and local web/API smoke checks.
- The agent usually does not have direct access to Pioreactor hardware such as PWM, GPIO, pumps, serial sensors, or HAT peripherals.

Use this environment for:

- Fast iteration on Python structure, imports, Click registration, config defaults, published settings, UI descriptor YAML, and pure helper logic.
- Targeted pytest tests when the logic can be exercised without hardware.
- Local discovery checks like `.venv/bin/pio plugins list` and `.venv/bin/pio run --help`.

When hardware behavior matters, do not pretend local tests prove the full job. Add a handoff step: copy the plugin file and any UI YAML to a same-network Pioreactor, commonly with `scp` or `ssh`, then run on-device smoke checks.

Example deployment targets:

```text
~/.pioreactor/plugins/<plugin>.py
~/.pioreactor/plugins/ui/jobs/<descriptor>.yaml
```

## On-device development

This is an agent or shell running directly on a Pioreactor:

- Plugin modules live in `~/.pioreactor/plugins/`.
- UI descriptors live in `~/.pioreactor/plugins/ui/jobs/`.
- The device has access to real Pioreactor hardware and the real services that control it.
- The repo test harness is usually absent; do not assume `pytest`, source checkout paths, or `.venv/bin/pytest` exist.

Use this environment for:

- Real hardware smoke checks.
- `pio plugins list` discovery.
- `pio run <job_name>` startup and cleanup behavior.
- MQTT inspection with `pio mqtt`.
- UI descriptor checks through local API endpoints when the web service is running.

On-device validation should be conservative. Prefer short runs, explicit cleanup, and safe hardware defaults. If the job controls pumps, LEDs, heaters, stirrers, or external devices, verify the safe stop path before longer tests.

## Choosing validation

- If running repo-local: validate Python and UI shape locally, then state which hardware behavior still needs on-device verification.
- If running on-device: skip repo-only tests and validate through `pio plugins list`, `pio run`, MQTT, logs, UI descriptors, and physical behavior.
- If the user asks for a shareable plugin, include both workflows in the handoff: local development checks plus on-device install and smoke-test steps.
