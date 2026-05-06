---
name: pioreactor-automations
description: Create, update, debug, or review Pioreactor dosing, temperature, and LED automations, including automation families, config sections, UI descriptors, runtime execution strategies, published settings, lifecycle cleanup, and dosing shutdown safety.
---

# Pioreactor Automations

## Goal

Help Codex implement Pioreactor automations that match the existing dosing, temperature, and LED job architecture, choose the correct trigger model, and preserve runtime safety.

## Families

- Automations are split into 3 families: dosing, temperature, led under core/pioreactor/automations/.
- Each family is powered by a background job base class:
  - core/pioreactor/background_jobs/dosing_automation.py
  - core/pioreactor/background_jobs/temperature_automation.py
  - core/pioreactor/background_jobs/led_automation.py
- Shared automation execution helpers live in `core/pioreactor/automations/base.py`.


## Config.ini sections

Use section name `[<type>_automation.<automation_name>]`. Example:

```
[dosing_automation.turbidostat]
[dosing_automation.pid_morbidostat]
[temperature_automation.thermostat]
```

## UI yaml

### Automation chooser descriptors

 Path: `.pioreactor/ui/automations/<type>/*.yaml`
 Served by: `/api/automations/descriptors/<automation_type> in core/pioreactor/web/api.py`
 Schema: `AutomationDescriptor` in `core/pioreactor/structs.py`
 Fields:
    - display_name
    - automation_name
    - description
    - fields[] where each field has key/default/label/type/unit/disabled/options

- automation_name in Python class must match YAML automation_name.
- UI fields[].key should correspond to constructor args and/or published settings.
- Runtime mutability is governed by published_settings[...]["settable"], not by YAML alone.
- Do not add `skip_first_run` as a global UI field. If an automation needs it, expose it as an explicit field for that automation.


## Execution strategies

Pick the strategy that matches the automation's real trigger. Do not force event-like automations into a duration loop.

### Periodic automations

Use `self.run_every(duration, skip_first_run=...)` in `__init__` when the automation should run at a fixed cadence.

- `execute()` contains one automation decision/action.
- `run_every()` starts a `RepeatedTimer` after the job reaches its post-init phase.
- `set_duration()` reschedules the next periodic run based on `_latest_run_at`.
- Example shape: chemostat-style dosing, where each cycle exchanges a fixed volume.

### Event-triggered automations

Use passive MQTT listeners plus `self.trigger_run_once_from_event()` when the automation should react to fresh data.

- Let the base listener update cached values first, then trigger.
- Ignore retained MQTT messages for control decisions.
- Gate startup with a simple readiness flag if callbacks can arrive before constructor-specific fields are initialized.
- `trigger_run_once_from_event()` is non-overlapping. If an event arrives while `execute()` is running, it records one pending follow-up run.
- Example shape: turbidostat dosing reacts to selected biomass signal updates.

### Boundary-scheduled automations

Use a one-shot timer when the next useful run is a calculable boundary, not a fixed polling interval.

- Keep `execute()` as the current-state application.
- After applying state, schedule the next boundary.
- On setting changes, apply current state and reschedule.
- On sleeping/disconnected, cancel the active boundary timer.
- If assigning `_automation_strategy_start_callback`, the callback must be `Callable[[], None]`. Wrap methods that return `AutomationEvent | None` in a no-return callback.
- Example shape: light/dark LED cycle schedules the next light/dark phase transition.


## Shared execution rules

- Prefer `run_once()` over calling `execute()` directly. It handles READY gating, non-overlap, event logging, `latest_event`, and common exception handling.
- `execute()` should return an `AutomationEvent` or `None`.
- Use `wait_for_ready=False` only when the caller already knows the job is ready or is running from a controlled state transition.
- Avoid defensive compatibility shims for old automation APIs unless there is a current caller in this repo.
- Keep automation callbacks and timers explicitly cancellable in `on_sleeping()` / `on_disconnected()`.


### Subclassing existing automations

- Try to run `super().__init__(...)` immediately in the new `__init__`.
- Initialize any fields used by MQTT callbacks before they can be observed, or use a small readiness flag.
- Constructor args should accept `float | str` / `int | str` for UI and CLI inputs, then coerce once in `__init__` or setters.
- Published setting setters should apply live state changes when possible. Example: changing LED intensity while lights are active should update LEDs immediately.


## Dosing shutdown safety

- `DosingAutomationJob.on_disconnected()` must stop active pump jobs before waiting for automation timers to finish.
- `_continue_pumping_event` is cooperative: it prevents the next subdose, but does not interrupt a currently running pump action by itself.
- Shutdown order should be: set the cooperative stop event, publish stop messages to active pump jobs, then call shared timer cleanup.
