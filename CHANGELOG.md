### Upcoming

#### Enhancements

 - removed System tab from the Pioreactor's "Control" dialog. You can see (most) of this data on the Inventory page
 - added a Self-test tab back to the Pioreactor's "Control" dialog, and to the "Control all Pioreactors"
 - added `pio status` for a quick local health summary (identity, versions, MQTT, web API, Huey, jobs, storage)
 - improved `pio db`, `pio cache`, and `pio log` help output with clearer descriptions and examples
 - improved `pio workers status` to use unit API health checks for reachability and provide brief reasons when state/version are unknown
 - improved `pios` help output with clearer descriptions and examples for cluster actions
 - removed the redundant `--job` flag from `pios kill` (use `--job-name`)

#### Bug fixes

 - reused cached IR LED reference normalization per experiment when `ref_normalization=unity`, instead of always taking the first reading
 - improved unit API retry safety by returning in-progress responses when Huey task locks are held
 - improved API error messages with structured causes and remediation hints for agents and UI clients
 - fixed `pio run` command resolution to load plugins before looking up job commands

### 26.1.30

#### Highlights

 - Run calibrations from the UI.
 - New Protocols page with guided calibration sessions, step-by-step instructions, and live charts.

#### Enhancements

 - Support for Pioreactor XR.
 - Faster *Stop* commands in the UI, plugin listing, and data exports.
 - Added dosing start/stop events to `dosing_automation_events`, including exports.
 - Added unit-relative IR LED reference normalization for OD readings via `ref_normalization=unity`. This should align different Pioreactors to similar starting values, especially v1.5 models. However, this changes OD levels, so existing OD calibrations are not adjusted automatically.
 - New query pattern for faster Experiment Overview chart loading; large datasets may show randomized sampling in time series. Let us know if this is too distracting. Max point targets per series increased to 1400.
 - OD calibrations now support multiple photodiode angles; `pio calibrations run --device od` can emit per-angle calibrations for 45/90/135.
   - Added an update helper to migrate legacy OD calibrations into per-angle devices.
 - Calibration protocols are now exposed via API.
 - When a Pioreactor model is changed, a (non-blocking) hardware check is performed.
 - You can now restart the web server (lighttpd) and the background task queue, Huey, from the UI. Go to Leader -> "Long-running jobs", and see the "web server and queue" line.
 - Added spline and akima curve support for calibrations, including OD standards sessions and calibration charts.
 - `pio calibrations analyze` now supports `--fit poly|spline|akima`. You can use this to refit a dataset to a spline or akima curve.
 - Added estimator artifacts alongside calibrations, including OD fusion estimators stored under `storage/estimators` and managed via the calibration session flow. Estimators are a generalized calibration for more complex algorithms. Calibrations will be restricted to 1D models.
 - New unit APIs for estimators:
   - `/unit_api/estimators/<device>`
   - `/unit_api/estimators/<device>/<estimator_name>`
 - Faster startup and shutdown of Pioreactor jobs.
 - Charts on Experiment Overview now scale with window size.
 - New Estimators page in the UI.

#### Breaking changes
 - Moved Self-test to the Inventory page. Pioreactors no longer need to be assigned to an experiment to run self-test.
 - Removed `/api/workers/<pioreactor_unit>/configuration`; use `/api/units/<pioreactor_unit>/configuration`.
 - Self-test logs are now part of `$experiment`.
 - Calibration flow modules were merged into protocol modules; old import paths like `pioreactor.calibrations.pump_calibration` and `pioreactor.calibrations.od_calibration_*` are removed.
 - Removed experimental pump-detection failure handling from chemostat and turbidostat.
 - OD calibration devices are now per-angle (`od45`, `od90`, `od135`) instead of just `od`. Physically, this changes the calibration directory in `~/.pioreactor/storage/calibrations/od` to  `~/.pioreactor/storage/calibrations/{od45,od90,od135}`. Existing `od` calibration files and active calibrations are migrated during the update.
 - Self-test no longer creates a stirring calibration.
 - OD reading charts in the UI previously had a sensor label next to the unit, ex: `worker01-2`. Now it is the corresponding angle from `config.ini`. Note: only the global `config.ini` is used, not specific `unit_config.ini` files.
 - New OD and stirring calibrations are now fit with a akima, and not a polynomial.
 - Calibration curve data is now serialized as tagged structs (`poly`/`spline`/`akima`) instead of raw lists. `curve_type` is removed and existing calibration files are migrated during the update.
 - Reorganized calibration protocol modules into `core/pioreactor/calibrations/protocols/` and extracted a `registry.py` for protocol registration.
 - Removed OD calibration using a single vial.


#### Bug fixes

 - Fix self-test logging closing prematurely.
 - Fix floating point error at the boundary of OD calibrations.
 - Fix runtime forward-reference errors in type annotations after dropping `__future__` imports.
 - Fix timeouts being too short on some UI export operations.
 - Re-save calibration files on `pio calibrations analyze` confirmation even when the curve is unchanged.
 - UI now logs _all_ warnings and errors, including from the web backend.
 - Fix Mosquitto's pw.txt file.

### 25.12.10

#### Enhancements

  - Added a `pio jobs` command group with `running`, `list`, `info`, and `remove` subcommands to inspect and tidy job records, including published settings.
#### Breaking changes

  - `pio job-status` has been replaced by `pio jobs info`.
  - changed `/unit_api/jobs/stop` from using query params to json body.

#### Bug fixes

 - fix OD blank not being able to be run.
 - OD calibration now clamps out-of-range voltages to the OD values paired with the calibration’s voltage extrema, preventing inverted mappings on non-monotonic curves.
 - Images ship with DAC43608 library (missed the previous OS jump!)
 - Improvements to "Updating your model" on first boot.
 - Fix /pioreactor page crashing if a worker is inactive in the experiment.
 - Fixed clock syncing on the cluster

### 25.11.19

#### Enhancements

 - Added `pio job-status` for a quick view of running jobs.
 - Easier time syntax for experiment profiles!

   1. Use the `t` field to specify times using suffixes, like `15s`, `1m`, `2.5h`
   2. In `repeat` blocks, `every`  replaces `repeat_every_hours`, and `max_time` replaces `max_hours`. Both the same time syntax above.
   3. In `when` blocks, `wait_until` replaces `condition`.
   ```
   experiment_profile_name: demo_stirring_repeat

   metadata:
     author: Cam Davidson-Pilon
     description: A simple profile that starts stirring, increases it every 5min, and stops when the RPM exceeds 2000.

   common:
     jobs:
       stirring:
         actions:
           - type: start
             t: 0
           - type: repeat
             t: 5m
             every: 5m
             actions:
               - type: update
                 t: 0.0s
                 options:
                   target_rpm: ${{::stirring:target_rpm + 100}}
           - type: when
             t: 0s
             wait_until: ${{::stirring:target_rpm > 2000}}
             actions:
                - type: stop
                  t: 0s
   ```
   This is now the preferred way (though the old syntax isn't going away), and docs will be updated to reflect this.


#### Bug fixes

 - Cluster CLI commands now use `click.Abort()` (instead of bare `sys.exit`) so failed prompts, copy/install operations, and OD blanking exit cleanly with Click’s messaging.
 - Background jobs now only clear MQTT/db cache entries for attributes that were actually set, preventing accidental removal of unset metadata.
 - Dodging jobs keep their OD-reading interval topic published even if a second OD reader attempts to start and fails, so dodging continues uninterrupted.
 - Fix `pios update ...` breaking the web server from starting. (`pio update` is fine)


### 25.11.12

#### Highlights

 - Added support for Pioreactor v1.5.
 - Upgrade to Trixie Debian 13!
 - New Pioreactor architecture:
    - New environment variable file /etc/pioreactor.env
    - The old `pioreactorui` Python package is now part of the `pioreactor` Python package, under `pioreactor.web`
    - Moved temporary files from /tmp to /run/pioreactor/
    - New `pioreactor-web.service` to handle both `huey.service` and `lighttpd.service`

#### Enhancements

 - `pioreactor.hardware`: reworked GPIO, PWM, and I2C configuration to load from layered YAML mods so new HAT+model combinations can be described without code changes. See new ~/.pioreactor/hardware directories.
 - `pioreactor.hardware`: constants are now resolved lazily through accessor functions (e.g., determine_gpiochip(), get_pwm_to_pin_map()); direct module constants remain but are deprecated shims that emit warnings.
 - Export images (PNGs and SVGs) of the Overview's and Calibrations' charts.
 - MCP server: added tools for creating experiments and managing worker assignments.
 - Show and hide calibration curves in Calibrations page by clicking the dot beside the calibration (similar to the Overview page).
 - Adding `pio workers update-model <unit> -m <name> -v <version>` to leader's CLI.
 - Added time-window and time-format options to the individual Pioreactors pages.
 - New workflow to set your Pioreactor leader-worker model on first load of the UI.
 - Add new APIs and MCP tools via plugins. Example: drop the following in your ~/.pioreactor/plugins folder:
   ```python
# -*- coding: utf-8 -*-
from __future__ import annotations
from pioreactor.plugin_management import get_plugins
from pioreactor.web.plugin_registry import register_mcp_tool

__plugin_name__ = "mcp-plugins"
__plugin_version__ = "0.1.0"
__plugin_summary__ = "Adds convenience MCP utilities for Pioreactor plugin introspection."
__plugin_author__ = "Cam DP"


@register_mcp_tool()
def list_installed_plugins():
    """
    Return metadata for installed Pioreactor plugins registered with the system.
    """
    plugins = get_plugins()
    details = [
            {
            "name": name,
            "version": plugin.version,
            "summary": plugin.description,
            "author": plugin.author,
         } for name, plugin in plugins.items()
    ]
    return {"plugins": details}
   ```
 - New import of system files (the `~/.pioreactor` directory) into Pioreactors. This means that it's easy to "back up" a pioreactor (leader or worker), and then reupload this to a (new) pioreactor in your cluster via the import system. This is available on the Inventory page.
 - support for up to four PDs.

#### Breaking changes

 - Changed `start_od_reading` API. It now accepts a dict instead of args for each PD position.

### 25.9.18

 - Experiment profile editor: added a searchable capabilities browser. You can now search across available jobs, automations, actions, and options directly in the editor. This should make building and editing profiles faster and reduce syntax errors.
 - Experiment Overview charts: no longer hide older data on long experiments. Instead, each series is downsampled on the client to a maximum of 720 points while preserving trends, regardless of experiment length. For very large clusters this may increase initial load time — narrowing the time range or hiding unused series can help if you notice slowness.
 - Eye-spy optics: initial support is included. If detected, the OD reading job can use it via the existing interfaces. Nothing changes if you don’t have this hardware connected; more documentation will follow.
 - Inventory export: from the Inventory page, you can export a worker’s `~/.pioreactor` directory as a zip. The Leader page also includes an export for the leader’s `~/.pioreactor`. This is useful for backups, support, or migration. Review the archive before sharing — it may contain configuration and credentials.
 - Pump scripting: `pio run pumps ...` now accepts a `sleep` step to pause between actions. Example: `pio run pumps --media 2 --sleep 1 --waste 1.5` runs media for 2 mL, waits 1 s, then runs waste for 1.5 mL. In experiment profiles, you can repeat actions by suffixing keys with `_`, for example:
   ```yaml
   jobs:
     pumps:
       actions:
         - type: start
           options:
             media: 2
             sleep: 1
             waste: 1.5
             sleep_: 2   # repeat keys by adding underscores
             waste_: 0.5
   ```
 - Advanced config for automations: the UI’s “Advanced” menu (temporary config overrides at start) is now available when launching automations, not just individual jobs. The options shown come from the `[<job_name>.config]` section.
 - CLI: added leader-only experiment management commands — `pio experiments create <NAME>`, `pio experiments list`, and `pio experiments delete <NAME>`.

#### Bug fixes

 - Restored live updates in real‑time charts in the UI (regression fixed).
 - Corrected timestamps on exported dataset folders in the archive.
 - Removed cases of duplicate log lines shown in the UI.
 - MCP now correctly respects configured notification methods.
 - Fixed model selection in the “Add a new Pioreactor worker” dialog in Inventory.
 - For leader-only Pioreactors, fixed leaders not showing up in "Cluster clocks" (and likely other places)

### Breaking changes
 - Turbidostat now enforces `duration = 0.25s` for its frequent checks. The UI already used this value; CLI runs will now match it for more consistent behavior.


### 25.8.14

#### Highlights

* **Custom Bioreactor Models**
  Our community has been incredibly creative in adapting Pioreactor hardware and software for different vessel types. Now, you can officially add your own custom bioreactor models to the Pioreactor software!
  Place your model definitions as yaml files in the new `.pioreactor/models/` directory. For example:

  ```yaml
  model_name: custom_100ml
  model_version: "1.0"
  display_name: "Custom 100 mL, v1.0"
  reactor_capacity_ml: 100.0
  reactor_max_fill_volume_ml: 95.0
  reactor_diameter_mm: 50.0
  max_temp_to_reduce_heating: 80.0
  max_temp_to_disable_heating: 85.0
  max_temp_to_shutdown: 90.0
  ```

  Example file name: `custom_100ml.yaml`

  This information is used throughout the software (including the UI) to support different shapes, sizes, and safety limits. Tell us what else you’d like supported!

* **New MCP Server (Experimental)**
  You can now run an MCP server alongside your leader’s web server. It adds a new SSE-based endpoint at:

  ```
  http://<leader-address>/mcp/
  ```

  This exposes some Pioreactor tools in real time. It’s still experimental — your feedback and suggestions for additional tools/resources are welcome!



#### Enhancements

* Added **Time Range filter** to the **Export Data** UI page.
* The **“Add a new Pioreactor worker”** dialog now automatically scans for and lists local workers available to join your cluster.
* New `config.ini` option:

  ```
  [od_reading.config]
  duration_between_led_off_and_od_reading = <seconds>
  ```

  This adjusts the pause between turning off LEDs and taking an OD snapshot.
* `pios X --experiments <experiment>` now lets you target workers by experiment from the leader CLI.
* More CLI options are available for jobs with `settable: True` `published_setting`s.
* New API endpoints:

  * `/unit_api/capabilities`
  * `/api/units/<pioreactor_name>/capabilities`
    These provide detailed information about what each Pioreactor can run.



#### Breaking changes

* API changes:

  * `api/units/<unit>/configuration` response format updated.
  * Settings endpoint now scoped to experiments:

    ```
    /api/workers/unit1/jobs/settings/job_name/stirring/experiments/<exp>
    ```
  * Removed: `/api/workers/jobs/stop/experiments/<exp>`
    Use: `/api/workers/$broadcast/jobs/stop/experiments/<exp>`
  * Removed: `/api/experiments/<experiment>/jobs/settings/job_name/<job_name>`
    Use: `/workers/$broadcast/jobs/settings/job_name/<job_name>/experiments/<experiment>`
* `pio logs` no longer follows by default — use `-f` to follow.
* **Developers:** We’ve merged our three main repositories (`pioreactor`, `pioreactorui`, `pioreactorui_frontend`) into a single monorepo: `pioreactor`. The old repos will be archived, and update code in `pio.py` will now point to the new repo. If you have branches on the old repos, rebase onto `pioreactor`. Discussion: [GitHub issue #576](https://github.com/Pioreactor/pioreactor/issues/576).



#### Bug fixes

* Fixed default sorting when exporting CSV.
* Fixed crash in UI profile editor.
* Fixed pumps not shutting down correctly if active when `dosing_automation` stopped.
* Fixed cleanup issue in growth rate calculation.
* Fixed plugins page crashing when a plugin doesn't have a homepage associated to it.

### 25.7.2

🔥 hot fix release

#### Bug fixes
 - Fix error when `target_rpm_during_od_reading` is 0 and dodging is active.
 - Fix exporting pioreactor unit labels dataset.
 - Fix LED not working when booting a fresh worker.
 - Fix for plugins that use the "dodging" behaviour. Your air-bubbler plugin probably broke - this fixes it.

### 25.6.25

#### Enhancements
 - We previously introduced the ability for stirring to "dodge" OD reading by turning itself off during an OD snapshot. This proved useful, but users wanted the generalized ability to modify the RPM to any value during a snapshot. For example, slow down the RPM during a snapshot, instead of stopping stirring. Another use case is to set the RPM during a snapshot to be equal to the RPM when an OD calibration was performed. We've introduced two new stirring configuration parameters, only used when dodging is active:
   1. `target_rpm_during_od_reading`: the RPM when an OD snapshot is performed.
   2. `target_rpm_outside_od_reading`: the RPM outside a snapshot.
   We highly recommend having a stirring calibration active while using these.
 - There's a new "Advanced" start option in the UI to modify configuration temporarily when starting a job. The options shown are from the section `[<job_name>.config]`. This is useful for changing different configurations without changing the config files.
 - The above uses a new convention in `pio run` CLI command. You can provide configuration overrides with the `--config-override` option. Example:
   ```
   pio run --config-override od_reading.config interval 0.1 od_reading
   ```
   or
   ```
   pio run --config-override stirring.config initial_duty_cycle 25 --config-override mqtt username pp stirring
   ```
 - You can even use config overrides in experiment profiles (must be applied to the `start` action.)
   ```yaml
   common:
     jobs:
       od_reading:
         actions:
            - type: start
              hours_elapsed: 0.5
              config_overrides:
                samples_per_second: 0.1
                ir_led_intensity: 70
            ...
   ```
 - We moved our Extended Kalman Filter code out of this repo into it's own Python library: [grpredict](https://github.com/Pioreactor/grpredict).
 - Chemostat modal in the UI now shows the computed dilution rate
 - New "Duplicate" profiles button.
 - **Experimental**: Adding an experimental new feature that will detect a pump malfunction by comparing the OD before and after dosing. If the post-OD falls outside some expected bound (default is 20%), the dosing is paused until a user comes to unpause it. To enable this feature, set `dosing_automation.config` parameter `experimental_detect_pump_malfunction` to `True`.
    - This only applies to the current implementations of `turbidostat` and `chemostat` in our software.
    - This feature relies on 1) Accurate initial volume (inputted when you start the automation), 2) accurate pump calibrations, 3) clear media
 - Calibration charts have new crosshairs
 - The config `[mqtt]`  `broker_address` can now be a list of addresses, separated by `;`. Example:
   ```
   [mqtt]
   broker_address=pio01.local;100.119.150.2;localhost
   ```
 - Performance improvements
 - Backing up database now checks if the worker and local machine have enough disk space, and skips if not.

#### Breaking changes
 - In configuration, `[stirring.config]` parameter `target_rpm` is renamed to `initial_target_rpm`. This is better for letting users know that the RPM can be changed during a run.
 - floats are rounded to 12 decimals points in data exports.
 - localtime in data exports have subsecond precision.
 - Changed dosing automation variables names:
  - `max_volume` to `max_working_volume_ml` (also changed in config.ini)
  - `liquid_volume` to `current_volume_ml`
  - Chemostat and Turbidostat automations stopped using `volume` kwarg and now use `exchange_volume_ml`.
  - the chart `liquid_volumes` is renamed `current_volume_ml`. This should be updated in your config.ini under `[ui.overview.charts]` if you are using that chary.

#### Bug fixes
 - included new export dataset yaml for raw OD readings. This was missed in a previous release.
 - experiment profiles now check the syntax of nested actions before starting the execution.

### 25.6.3
(hotfix patch)

#### Bug fixes
 - update Adafruit-Blinka to fix USB issue.
 - Fix for HardwarePWM on RPi5 on linux kernel 6.6

### 25.5.22

#### Enhancements
 - new _System logs_ under _Inventory_ to track logs happening outside of experiments in your cluster.
  - Better organization of logs in the UI. System logs, like calibrations, worker additions, etc. won't show up on the Overview page.
 - Exported data zips have folders for each dataset requested.
 - Improvements to the Kalman filter. For users using the growth-rate model with media dosing, you should see improvements to your growth-rate time series. We recommend the following configuration:
 ```
[growth_rate_kalman]
# obs_std ↑ smooths growth rate, rate_std ↑ more responsive growth rate
obs_std=1.5
od_std=0.0025
rate_std=0.25
 ```
  **Note: the acceleration term is removed**
 - Added the column `hours_since_experiment_created` to dataset exports that details hours since experiment was created.
 - A running pump now fires off an incremental dosing event every N seconds (N=0.5 currently) to tell the software its progress. Previously, we would fire off a single event that represented the total amount moved. This is most noticeable when watching the vial volume change over time (looks more accurate over a short period).
 - When a pump runs, it _first_ fires off a dosing_event, which stores information about how much liquid is moved. However, if the pump is stopped early, there was no correction issued to the amount of liquid actually moved. Now, when a pump is stopped early, a _negative_ volume is sent s.t. the delta between the initial amount and new amount is equal to the dosed amount (so when you sum up the volume changes, you get the actual change, as expected).
 - Performance optimizations
 - New image installs only:
   - updated base OS to the latest 25-05-06 Raspberry Pi OS. The big change is using Linux kernel 6.12.

#### Bug fixes
 - fixed stir bar not spinning on Pioreactor page (UI) in some cases
 - alert user if their OD reading is constant before starting the growth-rate calculator, which would break things.
 - alert user if their software is installed in a non-standard location. If so, try `pip uninstall pioreactor -y`.
 - Added a warning if the OD calibration is invalid (ex: a constant line)
 - Fix for Raspberry Pi 5 using upstream Adafruit libraries.



### 25.5.1

#### Enhancements

 - new Upload Calibration dialog in the UI

#### Breaking changes

 - new OD calibrations are of type `od600` (instead of `od`). Nothing needs to change for the user.

#### Bug fixes

 - stirring calibration was using too many points from the lower bound, this is fixed.
 - fix for stirring calibration in the self-test creating an empty file
 - Fix custom charts that were not fetching from the database correctly due to the backend table being a sqlite3 view (VIEWs don't have ROWID, which was breaking a filter).

### 25.4.11

#### Bug fixes
 - Fix for heater PCB not shutting down correctly.

### 25.4.9

#### Bug fixes
 - Fix OD Reading not displaying correctly on Pioreactor pages
 - Fix duplicates in Raw OD Reading chart's legend
 - Improvements to pump calibration flow that will ask user what volumes they wish to calibrate for.
 - Fix self-test "REF is correct magnitude"
 - self-tests don't use calibrated OD readings anymore.

### 25.4.3

#### Enhancements

- **Support for Pioreactor 40mL**
  - UI and backend now accommodates the new Pioreactor 40mL. Change the Pioreactor model on the Inventory page.
- **Device models and versions now tracked in the database**
  - Models and versions for each Pioreactor are now stored in the `workers` database table. We're deprecating the `[pioreactor]` section in `config.ini`. You can manage models and versions on the **Inventory** page.
- **Improvements to dosing automation settings**:
  - When starting a dosing automation, you can set the initial and max culture volumes.
- **Raw vs. calibrated OD readings now separated**
  - When a calibration is applied in the `ODReading` job:
    - New MQTT topics are published:
      - `od_reading/raw_od1` and `od_reading/raw_od2` for **raw** (un-calibrated) values
      - `od_reading/calibrated_od1` and `od_reading/calibrated_od2` for **calibrated** values
  - The raw readings will be stored in new database tables, `raw_od_readings`. The calibrated values still occupy the table `od_readings`.
  - Existing topics like `od_reading/od1`, `od_reading/od2`, and `od_reading/ods` remain unchanged, but note they may contain either calibrated or raw data depending on calibration status.
  - To display a chart of the raw OD readings when a calibration is being used, switch the config entry `raw_optical_density` from `0` to `1` in the section `[ui.overview.charts]`

#### Breaking changes

- **Changes to `pio workers add`**
    - This command has been updated to better reflect the new model/version management.
- **Removed config parameter `max_volume_to_stop`.**
    - This is now hardcoded into the software. For 20ml, it's 18ml, and for 40ml, it's 38ml.

#### Bug Fixes

- Fixed occasional crash on the **Overview** page in the UI.
- Stirring dodging now correctly respects the first OD reading.
- Stirring (and other software PWM-based jobs) now clean up properly more often on disconnect.
- Fixed issue where dodging background jobs would run a final, incorrect `action_to_do_before_reading` after OD reading stops.
- The OD calibration flow now correctly ignores existing calibrations when creating a new one.
- UI page `/pioreactors/<some_unit>` now uses that unit's specific configuration from `config_<some_unit>.ini`.
- Fix error "cannot schedule new futures after shutdown" when stopping a dosing automation during a pump execution.
- Reverted a change to job's exit protocol introduced in 25.3.5 that would cause on_disconnected to run twice sometimes.
- Fixed "manual adjustments" pump actions not firing an MQTT event.
- Fixed OD calibrations using the wrong min, max thresholds.
- `pio calibrations analyze --device od` will use regression weights for OD calibrations (like they do _during_ the OD calibration)

### 25.3.5

#### Enhancements
- **New faster ADC firmware with less noise**
  - Upgraded ADC firmware improves signal processing speed and reduces measurement noise, leading to more reliable readings for all sensors.
- **`led_intensity` is now registered in our database**
  - This means that running `pio kill --all-jobs` (and related `pio kill` commands) will now also turn off all LEDs, ensuring a complete shutdown of active processes.
- **New option in `pio workers add` to specify an IPv4 address**
  - When adding a new worker, you can now explicitly provide an IPv4 address instead of relying on the default `hostname.local`. This is useful in networks where mDNS resolution is unreliable or unavailable. Ex: `pio workers add <name> -a 192.168.0.3`
- **New time option on the Overview page: "Now" for only real-time data**
  - The UI now has a “Now” option that filters out historical data, displaying only real-time sensor readings and status updates.
- **Logs for experiment profiles now include an action step number**
  - Each log entry related to an experiment profile now contains a step number, making it easier to track progress and diagnose issues in multi-step workflows.
- **Improved outlier detection in nOD and growth rates**
  - Our outlier detection algorithms for normal optical density (nOD) and growth rates have been refined, reducing false positives and improving tracking accuracy during experiments.
- **Changing OD readings interval programmatically**
  - OD Reading job now exposes `interval` as a editable published_setting. For example, you can PATCH to `http://pioreactor.local/api/workers/<pioreactor_unit>/jobs/update/job_name/od_reading/experiments/<experiment>` with body:
    ```
    {
      "settings": {
        "interval": 10
      },
    }
    ```
    to change OD readings interval to 10s.

#### Breaking Changes
- **`id` → `job_id` in `pio_metadata_settings` table**
  - Database schema update: The primary identifier column in `pio_metadata_settings` has been renamed to `job_id`.
- **Changed the scaling of `smoothing_penalizer`**
  - The `smoothing_penalizer` parameter now operates on a scale that is **~100x lower** than before.
- **Deprecation of `/unit_api/jobs/stop/...` endpoint**
  - The `/unit_api/jobs/stop/...` API endpoint is being deprecated in favor of using query parameters:
    - Instead of `/unit_api/jobs/stop/job_name`, use `/unit_api/jobs/stop/?job_name=...`.
    - The special case `/unit_api/jobs/stop/all` remains valid and unchanged.
- **Timestamp precision change: From `xxxxx` milliseconds → `xxx` milliseconds**
  - All timestamps will now be stored with three-digit millisecond precision instead of five. This change optimizes storage efficiency and speeds up queries while maintaining sufficient accuracy for most use cases.

#### Bug Fixes
- **Fix for "More" button in the Logs UI page**
  - Previously, clicking "More" in the Logs UI would default to "Standard" log level instead of retaining the selected filter. Now, it correctly uses the log level chosen by the user.
- **Multiple experiment profiles no longer overwrite each other in MQTT**
  - Previously, running multiple experiment profiles could cause MQTT messages to overwrite each other. This is now fixed, but note that the new MQTT topic format introduces `job_id`, deviating from our usual topic structure.
- **Fix for API returning incorrect responses for Huey-related tasks**
  - API responses related to background tasks (e.g., adding a new Pioreactor, syncing configs, updating firmware) were sometimes incorrect or missing details. This has been fixed.
- **Correction to `od_reading.config`'s `smoothing_penalizer` scaling error**
  - A miscalculated scaling factor in `od_reading.config` caused the smoothing factor to be larger than intended. This has been corrected, and your `config.ini` file has been automatically updated to reflect the new values.
- **Fix for missing log events in Event Logs after worker unassignment**
  - Some log events (such as clean-up and assignment events) were missing when they occurred after a worker was unassigned. These now appear correctly. Additionally, some unrelated log entries that were mistakenly displayed have been removed.
- **Scaling bug fix in the extended Kalman filter affecting nOD detection**
  - A bug in the extended Kalman filter was **causing outlier detections too frequently**. In extreme cases, these detections could compound, driving nOD values negative and corrupting the filter’s internal state. This issue has been fixed with a new, more stable filtering algorithm that significantly improves robustness.

### 25.2.20

**Important**, any OD calibrations made on software versions 25.1.21 and 25.2.10 have incorrect metadata, and it needs to be updated. Use this hot fix release to fix them. You'll still need to rerun:

```
pio calibrations analyze --device od --name <cal name>
```

to recreate the calibration curves.


- Hot fix for OD Calibrations bug.

### 25.2.11

### Enhancements

- **New OD Calibration**: Introduced a new OD calibration using standards (requires multiple vials). Run:
  ```
  pio calibrations run --device od
  ```
  Inspired by the plugin by @odcambc.

- **UI Improvements**:
  - Improved chart colors.
  - Added the ability to choose the level of detail on the new Event Logs page.

- **New OD Reading Option**: The OD reading CLI now includes a `--snapshot` option to start the job, take a single reading, and exit. This is useful for scripting.

- **New Pump Control CLI**: Introduced a new CLI for pumps:
  ```
  pio run pumps --media 1 --waste 2
  ```
  This command will add 1ml of media and remove 2ml of waste. The order matters, and pumps can be specified multiple times:
  ```
  pio run pumps --waste 2 --media 1 --waste 2
  ```
  This new CLI is really useful for experiment profiles. For example, a chemostat can be "programmed" as (but don't actually do this, using a dosing automation):
  ```yaml
  common:
    jobs:
      pumps:
        actions:
          - type: repeat
            hours_elapsed: 0 # start immediately
            repeat_every_hours: 0.5 # every 30m, run the following actions
            actions:
              - type: start
                hours_elapsed: 0
                options:
                  media: 1
                  waste: 2

  ```

- **Experiment & System Enhancements**:
  - Initial support for 40ml model.
  - Ability to run multiple experiment profiles per experiment.
  - Users can now specify which Pioreactor to update on the Updates page (available only with release archives).
  - Stirring calibration is now included as part of the self-test.
  - Improved stirring job handling when OD readings have long pauses.

- Previously, if a worker’s web server was down, an update would be blocked. Now, the leader will first attempt the web server, and if a 5xx error is observed, it will attempt SSH communication instead.

---

### Web API Changes

- Introduced:
  - `GET /unit_api/jobs/running/<job>`
  - `GET /api/experiment_profiles/running/experiments/<experiment>`

---

### Breaking Changes

- **Calibration Structs**:
  - `predict` → `x_to_y`
  - `ipredict` → `y_to_x`
  - This change makes naming clearer.

- **Plugin Migration** (Upcoming):
  - Plugins should migrate from `click_some_name` to auto-discovered plugins by importing `run`.
  - Example migration:
    ```python
    import click
    from pioreactor.cli.run import run

    @run.command("my_name")
    @click.option("--my_option")
    def my_name(my_option):
        ...
    ```

- **Select workers by experiment** (Upcoming):
  - Add `--experiments` option to pios commands to select all active workers assigned to the specified experiment(s).

### Bug Fixes

- Fixed UI not displaying third-party calibrations.
- Experiment profiles now directly use `unit_api/`, potentially mitigating Huey worker stampedes when starting multiple jobs.
- Fixed `pio calibrations run ... -y` not saving as active.
- Fixed manual dosing issues in the UI.
- Fixed manual log recording in the UI.
- There was a race condition between `monitor` and a db creation job that was preventing the `monitor` job from starting. Awkwardly, this only seemed to happen on power cycles, and only _sometimes_. This escaped our testing. We've fixed it by improving how we initialize the dbs, and how we connect to them.


### 25.1.21

#### Highlights
 - New UI updates:
   - An `Event Logs` page for seeing the logs generated by your Pioreactors
   - A detailed overview of your cluster's leader-specific duties on the new `Leader`'s page.
     - See the Leader's filesystem, logs, update cluster clocks, and view important running jobs.
   - View different Pioreactors' plugins on the `Plugins` page, and install to specific Pioreactor vs entire cluster.
   - Manage your calibrations from the UI's new `Calibrations` page.
     - View existing calibrations, set active calibrations, and download calibration files.
 - New calibrations API. A calibration now creates a YAML file as an artifact, stored in `~/.pioreactor/calibrations`. This makes editing, creating, sharing, and transferring calibrations much easier.
  - There's also a new CLI for calibrations:
    ```
    Usage: pio calibrations [OPTIONS] COMMAND [ARGS]...

      interface for all calibration types.

    Options:
      --help  Show this message and exit.

    Commands:
      delete      Delete a calibration file from local storage.
      display     Display the contents of a calibration YAML file.
      list        List existing calibrations for the given device.
      run         Run an interactive calibration assistant for a specific device.
      set-active  Mark a specific calibration as 'active' for that device
      analyze     Analyze the data from a calibration.
    ```

    For example, to run a pump calibration, use `pio calibrations run --device media_pump`. View all your media pump calibrations with:  `pio calibrations list --device media_pump`.

   - For now, the actual calibrations are the same protocol as before, but in the near future, we'll be updating them with new features. Adding this unified CLI and YAML format was the first step.


#### Web API changes
 - New API to retrieve and set clocks on Pioreactors
   - GET `/api/units/<pioreactor_unit>/system/utc_clock`
   - GET `/unit_api/system/utc_clock`
   - POST `/api/system/utc_clock`
   - POST `/unit_api/system/utc_clock`
 - New log APIs
   - GET `/api/experiments/<experiment>/recent_logs`
   - GET `/api/experiments/<experiment>/logs`
   - GET `/api/logs`
   - GET `/api/workers/<pioreactor_unit>/experiments/<experiment>/recent_logs`
   - GET `/api/workers/<pioreactor_unit>/experiments/<experiment>/logs`
   - GET `/api/units/<pioreactor_unit>/logs`
   - POST `/workers/<pioreactor_unit>/experiments/<experiment>/logs`
 - New calibrations APIs
   - GET `/api/workers/<pioreactor_unit>/calibrations`
   - GET `/unit_api/calibrations`
   - GET `/unit_api/active_calibrations`
   - GET `/api/workers/<pioreactor_unit>/calibrations/<device>`
   - GET `/unit_api/calibrations/<device>`
   - PATCH `/api/workers/<pioreactor_unit>/active_calibrations/<device>/<cal_name>`
   - PATCH `/unit_api/active_calibrations/<device>/<cal_name>`
   - DELETE `/api/workers/<pioreactor_unit>/active_calibrations/<device>/<cal_name>`
   - DELETE `/api/workers/<pioreactor_unit>/calibrations/<device>/<cal_name>`
   - DELETE `/unit_api/active_calibrations/<device>/<cal_name>`
   - DELETE `/unit_api/calibrations/<device>/<cal_name>`
   - POST `/unit_api/calibrations/<device>`
 - New API for plugins
   - GET `/api/units/<pioreactor_unit>/plugins/installed`
   - PATCH `/api/units/<pioreactor_unit>/plugins/install`
   - PATCH `/api/units/<pioreactor_unit>/plugins/uninstall`
 - Changed the `settings` API (see docs).
 - New `/api/units` that returns a list of units (this is workers & leader). If leader is also a worker, then it's identical to `/api/workers`
 - New `/api/experiments/<experiment>/historical_worker_assignments` that stores historical assignments to experiments
 - New Path API for getting the dir structure of `~/.pioreactor`:
   - `/unit_api/system/path/<path>`

### Enhancements
 - new SQL table for `historical_experiment_assignments` that stores historical assignments to experiments.
 - UI performance improvements
 - Better terminal plots
 - Customs charts in the UI are now downsampled like the other charts.
 - More logging in experiment profiles

### Breaking changes
 - `use_calibration` under `od_reading.config` is deprecated. Use the calibrations "active" state instead.
 - **Note**: by default, all calibrations are not active, even if they were "current" before. You must set them to be active.
 - removed Python library `diskcache`.
 - any stirring calibrations needs to be redone. On the command line, run `pio calibrations run --device stirring` to start the calibration assistant.
 - fixed typo `utils.local_persistant_storage` to `utils.local_persistent_storage`.
 - Kalman Filter database table is no longer populated. There is a way to re-add it, lmk.
 - moved intermittent cache location to `/tmp/pioreactor_cache/local_intermittent_pioreactor_metadata.sqlite`. This also determined by your configuration, see `[storage]`.
 - removed `pioreactor.utils.gpio_helpers`
 - removed `calibrations` export dataset. Use the export option on the /Calibrations page instead.
 - persistent storage is now on single sqlite3 database in `/home/pioreactor/.pioreactor/storage/local_persistent_pioreactor_metadata.sqlite`. This is configurable in your configuration.
 - When checking for calibrations in custom Dosing automations, users may have added:
   ```python
      with local_persistant_storage("current_pump_calibration") as cache:
          if "media" not in cache:
          ...
   ```
    This should be updated to (**Note** the spelling in `local_persistant_storage` changed, too!):

    ```python
        with local_persistent_storage("active_calibrations") as cache:
            if "media_pump" not in cache:
            ...
    ```

### Bug fixes
 - Fix PWM3 not cleaning up correctly
 - Fixed Stirring not updating to best DC % when using a calibration after changing target RPM
 - Fixed a bug that could cause OD calibrations to map a small voltage value to a max OD.
 - Fixed bug where dataset exports were not sorted correctly.
 - em-dashes are now replaced in config.ini on save.
 - Fixed a bug where errors on the Experiment Profiles page weren't properly displayed.

### 24.12.10
 - Hotfix for UI settings bug


### 24.12.5

#### Highlights
 - New export datasets improvements!
   - new export dataset API. The datasets on the Export Data UI page are now provided via YAML files on the leader's disk. This makes it easy to add new datasets to that UI to be exported. These YAML files can be added to `~/.pioreactor/exportable_datasets`.
   - new Export Data page in the UI. Preview datasets before you export them, and new partition options for the exported CSVs.
   - Plugins can now add datasets to the Export Data page. The plugin's datasets are automatically added to the Export Data page when installed.
 - Stirring can now pause itself during an OD reading. This is accomplished by "dodging OD readings". You can activate this feature by setting the `enable_dodging_od` to `True` in config.ini, under `[stirring.config]`. The replaces an older, less reliable plugin that was on our forums. Users have wanted this feature to have a very fast RPM between OD measurements (to get more aeration), and avoid noisy OD measurements. There's no reason to believe this will decrease the noise if using a "moderate" RPM though.

#### Enhancements
 - improvements to Dodging background job code, including the ability to initialize the class based on dodging or not.
 - better error handling for failed OD blank action.
 - better button state management in the UI.
 - a job YAMLs' published_settings can have a new field, `editable` (bool), which controls whether it shows up on the Settings dialog or not. (False means it won't show up since it's not editable!). Default is true. This _should_ align with the `published_setting` in Python's job classes.
 - you can add IPv4 addresses to the (new) `[cluster.addresses]` section to specify IPs for pioreactors. Example:
   ```
   [cluster.addresses]
   pio01=10.42.0.2
   pio02=10.42.0.3

   ```
   Note that the leader's address is automatically added in our software.
 - new installs only: updated RPiOS to version 2024-11-19
 - improvements to correlation self-tests

#### Bug fixes
 - Fixed "circulate X" actions in the Manage All dialog in the UI.

#### Breaking changes
 - moved all the temporary caches, which previously where their own sqlite3 dbs in `/tmp/` to `/tmp/local_intermittent_pioreactor_metadata.sqlite`. This shouldn't break anything unless you update _during_ an experiment - don't do that!

### 24.10.29

#### Enhancements
 - `dosing_automation.vial_volume` replaced with `dosing_automation.liquid_volume`. You can see the values by watching `pio mqtt -t "pioreactor/+/+/dosing_automation/liquid_volume"`  after starting a dosing automation.
 - Adding a SQL table for tracking `liquid_volume`.
 - Because we are now storing `liquid_volume` in the database, you can add charts in the UI that track the volume over time:
    1. Add the following yaml contents to `~/.pioreactor/plugins/ui/contrib/charts/liquid_volume.yaml`: https://gist.github.com/CamDavidsonPilon/95eef30189101da69f706d02ef28d972
    2. In your config.ini, under `ui.overview.charts`, add the line `liquid_volume=1`.
 - New dataset exports from the Export data page in the UI: calibrations and liquid-volumes.
 - Added a "partition by unit" option to the Export data page that will create a csv per Pioreactor in the export, instead of grouping them all together.
 - od calibrations can use the `--json-file` to edit calibration polynomial coefficients. In the json file, specify `curve_data_` fields with values of the curve's polynomial coefficients (leading term first), and set `curve_type` as `"poly"`. The routine will begin with that calibration curve displayed.
 - faster UI response times when starting jobs.
 - faster syncing configs.
 - faster copying files across cluster via `pio cp`.
 - faster clean up of jobs using PWMs.
 - new installs only: updated base RPiOS to 2024-10-22.
 - new database table in `/tmp/local_intermittent_pioreactor_metadata.sqlite` called `pio_job_published_settings` that stores the published settings for each job. This powers the next API endpoints:
 - New API endpoints for getting the current settings of a _running_ job:
    - Per pioreactor:
      - GET: `/unit_api/jobs/settings/job_name/<job_name>`
      - GET: `/unit_api/jobs/settings/job_name/<job_name>/setting/<setting>`
    - Across the cluster:
      - GET: `/api/jobs/settings/job_name/<job_name>/setting/<setting>`
      - GET: `/api/jobs/settings/job_name/<job_name>/experiments/<experiment>`
      - GET: `/api/jobs/settings/job_name/<job_name>/experiments/<experiment>/setting/<setting>`
      - GET: `/api/jobs/settings/workers/<pioreactor_unit>/job_name/<job_name>`
      - GET: `/api/jobs/settings/workers/<pioreactor_unit>/job_name/<job_name>/setting/<setting>`
   Ex: query the temperature of a Pioreactor: `curl http://pio01.local/unit_api/jobs/settings/job_name/temperature_automation/setting/temperature`


#### Breaking changes
 - `pio kill --name x` is now `pio kill --job-name x`
 - removed publishing published_settings metadata to mqtt. Ex `$properties`, `$settable`, `$unit`, `$datatype` are no longer being sent mqtt. This was never used, and just a bandwidth suck.

#### Bug fixes
 - fix for OD calibration graph showing "two lines" in the terminal display
 - fix for updating over the internet when a Pioreactor is on a `A.devX` or `B.rcY` release
 - `pio kill --all-jobs` will no longer kill long-running jobs from plugins (specifically, `logs2x` jobs.)
 - updating the UI software won't prematurely stop any currently running activities
 - correct ethernet mac address on RPi5s
 - We weren't passing all the OS environment variables when jobs were started from the UI. This is fixed now.
 - Fixed circulate media / alt. media in the UI.
 - Fixed manual dosing updates in the UI.



### 24.10.1

#### Enhancements
 - amount of data shown on charts is now a function of the OD sampling rate
 - allow for showing more than 16 workers in a chart.

#### Bug fixes
 - Bug fix for "Manage all" that would start activities in all Pioreactors, whether they were in the experiment or not.
 - Fix for bug when clicking a legend element it not hiding
 - `led_intensity` (i.e. changes to LEDs) now respect whether a worker is active or not.
 - Fix bug for UI crashing with "colors" error.
 - If a worker is referenced in a profile, but is not part of the current experiment, the actions will not be schedualed for it.



### 24.9.26

#### Enhancements
 - UI improvements to the experiment select box.
 - Better clean up of configs when a worker is removed from the cluster.
 - Improved UI loading time

#### Bug fixes
 - only show ipv4 in UI and in avahi aliases.
 - fixed experiment profile plugin checks.
 - fixed experiment profile display crashing the UI when editing plugins section.

#### Breaking changes
 - `pio clear-cache` renamed to `pio cache clear`
 - `pio view-cache` renamed to `pio cache view`
 - some more web API changes to endpoints that manage updates
 - We no longer use `monitor` to start jobs. This has a slowdown when changing LEDs or starting pumps, unfortunately, but generally better performance elsewhere.
 - `watchdog` job has been merged with `monitor`. `watchdog` no longer exists.

### 24.9.19

#### Highlights
 - Workers now have a webserver on them. This is one of the largest architectural changes to Pioreactor, and lays the foundation for better plugin, version, and calibration cluster management, plus future features.
   - As an example, in your browser, you can enter the url: http://some-worker.local/unit_api/jobs/running to see a list of jobs running on a worker.
   - Note: there is no interactive user interface for workers, just a web API
   - Previous actions that would involve SSHing from leader to a worker are replaced by web requests.

#### Bug fixes
 - fixed an issue where a calibrated OD reading would be mapped to max OD signal if it was too low.
 - fixed an issue where the Pioreactor UI would lock up if trying to create a new experiment with an existing name.
 - fixed Hours Elapsed not updating in Overview

#### Breaking changes
 - **Lots and lots of web API changes**. You'll want to review them on our docs: https://docs.pioreactor.com/developer-guide/web-ui-api
 - We no longer recommend the Raspberry Pi Zero (the original Zero, not the Zero 2.) since supporting a web server + pioreactor functions is too much for a single core.
 - `watchdog` is neutered. It used to try to "wake-up" a job, but this was flaky and causing more problems than it solved.
 - removed python library dependency `sh`
 - APIs that initiate a background task either return with the result, or return a task id that be be looked up at `/unit_api/task_status/`.
 - `pios update` now updates the UI too.

#### Enhancements
 - Better MQTT re-connection logic.
 - New `Manage Inventory` menu on the Inventory page that can be used for bulk actions.
 - `pio update` is a new command to update both the UI and app.
 - adding more network logs to `network_info.txt`
 - `pios` commands now return quicker since they post to the workers servers and don't wait around. You can view the status of the worker's by using the output from including `--json`.


### 24.8.22

#### Enhancements

 - `pio logs` now includes the UI logs (if run on leader).
 - introduce a new od_reading config,`turn_off_leds_during_reading`, which enables / disables turning off the other LEDS during an OD snapshot. By default, it is set to 1 (enables).
 - leader-only Pioreactors also have a `config_<hostname>.local` file now.
 - a new top-level section in experiment profiles, `inputs`, allows you to define parameters that can be used in expressions. This is useful if you are copy the same constant over an over again, and want a quick way to change it once. Example:

  ```yaml
  inputs:
    growth_phase_temp: 37.0
    stationary_phase_temp: 30.0
    od_threshold: 1.6

  common:
    jobs:
      temperature_automation:
        actions:
          ...
          - type: update
            hours_elapsed: 12.0
            if: ${{ ::od_reading:od1.od < od_threshold }}
            options:
              target_temperature: ${{ stationary_phase_temp }}
          - type: update
            hours_elapsed: 12.0
            if: ${{ ::od_reading:od1.od >= od_threshold }}
            options:
              target_temperature: ${{ growth_phase_temp }}

  ```

#### Bug fixes

 - more resilience to "UI state" diverging from "bioreactor state".  Often, this occurred when two jobs stared almost immediately (often a networking issue), and the last job would halt since it couldn't get the required resources, however any MQTT data would be overwritten by the last job. Now, multiple places in the request pipeline will reduce duplication and prevent two jobs from starting too close to each other.
 - improved stirring clean up when stopped in quick succession after starting.
 - if a network isn't found, the `monitor` job will not stall, but warn and continue.
 - fixed HAT warning for HAT-less leaders.

#### Breaking changes

 - the RP2040 firmware is now on i2c channel 0x2C (previously 0x30). This is to solve an annoying `i2cdetect` issue where the i2c channel would lock up.
 - the web server now writes its logs to the same location as the app: `/var/log/pioreactor.log`. Those wishing to keep the old location can use a new configuration parameter `ui_log_file` to `[logging]` section and set it to `/var/log/pioreactorui.log`.
 - removed `psutil` and `zeroconf` Python packages from new images. We replaced their functionality with built-in routines.
 - in config.ini, the section `od_config` renamed to `od_reading.config`, and `stirring` is `stirring.config`. When you update, a script will run to automatically update these names in your config.inis.

### 24.7.18

#### Enhancements

 - improvements to the UI's experiment profile preview.
 - `hours_elapsed()` is a function in profile expressions, which returns the hours since the profile started.
 - `unit()` can be used in mqtt fetch expressions. Example: `unit():stirring:target_rpm` is identical to `::stirring:target_rpm`. The latter can be seen as a shortened version of the former.
 - experiment profiles can have a `description` in the `job` field (i.e. at the same level as `actions`).
 - Updated Raspberry Pi OS image to 2024-07-04.
 - Vendoring the TMP1075 library, which also fixes the RPi5 error.
 - In places where the ipv4 is displayed (Inventory page, System tab, pio workers status, etc), *all* ipv4 addresses are displayed.

#### Breaking changes

 - remove the temperature_control, dosing_control, and led_control abstractions. These were introduced early in the Pioreactor software as a way to quickly change automations, but they have been more of a wort than a win. While working on the internals of experiment profiles recently, it became more and more clear how poor this abstraction was. The removal of them has some consequences and some backward incompatibilities:

  - updating experiment profiles: experiment profiles that have a `*_control` job will need to be updated to use `*_automation`, _eventually_. For now, we are allowing `*_control` in profiles: in the backend, we are renaming `*_control` to `*_automations`, but a warning will be produced. Later, we'll remove this renaming and profiles will need to be completely updated. Example:
    ```yaml
    experiment_profile_name: start_temp_control

    metadata:
      author: Cam DP

    common:
      jobs:
        temperature_control:
          actions:
            - type: start
              hours_elapsed: 0
              options:
                automation_name: thermostat
                target_temperature: 30
            - type: stop
              hours_elapsed: 12
        temperature_automation:
          actions:
            - type: update
              hours_elapsed: 6
              options:
                target_temperature: 35
    ```

    becomes:

    ```yaml
    experiment_profile_name: start_temp_control

    metadata:
      author: Cam DP

    common:
      jobs:
        temperature_automation:
          actions:
            - type: start
              hours_elapsed: 0
              options:
                automation_name: thermostat
                target_temperature: 30
            - type: stop
              hours_elapsed: 12
            - type: update
              hours_elapsed: 6
              options:
                target_temperature: 35
    ```

    - update plugins. For users using, specifically, the high-temp plugin, or temperature-expansion-kit plugin, new plugins will be released. Look on the forums, or documentation, for update instructions.

   The benefits of removing this abstraction is much less code, less overhead, easier developer experience, and overall simplification. Later, we may create a new abstraction, but now we are moving abstractions back to level 0.

 - `log` in experiment profiles now uses expressions instead of Python string formatting. For example: `The unit {unit} is running {job} in experiment {experiment}` should be replaced by expressions in the string: `The unit ${{unit()}} is running ${{job_name()}} in the experiment ${{experiment}}`. Note: `{job}` is now `${{job_name()}}`.
 - `cycle_media` and `cycle_alt_media` now publish dosing events, and will be recorded by dosing automations, and the db.


#### Bug fixes

 - When pausing temperature automations, the heater now turns off and stays off until unpaused. This is the intended behaviour.

### 24.7.5 & 24.7.6 & 24.7.7

Hotfix release for 24.7.3. This pins blinka to a specific version which does not install numpy.


### 24.7.3

#### Enhancements
 - A new live preview in the UI's experiment profile editor. This preview tool is useful for getting immediate feedback when writing a profile. We'll keep on adding to this to improve the edit-profile workflow - please send us feedback!
 - new `when` action type in experiment profiles that will execute an action (or list of actions) when some expression is true. For example, start a chemostat when a threshold OD is first achieved, log a message when event is triggered, or monitor a bioreactor parameter and execute an action if it goes out of bounds.
 - New config `turbidostat.config` that can be used to modify some internal turbidostat settings:
   ```
   [turbidostat.config]
   signal_channel=2
   od_smoothing_ema=0.5
   ```
 - Better user interaction on the Pioreactors page when the assigned experiment and "viewing" experiment are different.
 - Select / Deselect all Pioreactors to assign to an experiment faster.
 - Added `unit()` function to experiment profiles expressions that returns the unit name the expression is evaluated for. Ex: `if: ${{ unit() == worker01 }}`.
 - Added `job_name()` function to experiment profiles expressions that returns the job_name the expression is evaluated for. Ex: `if: ${{ job_name() == stirring }}`.
 - Added `experiment()` function to experiment profiles expressions that returns the experiment the expression is evaluated for. Ex: `if: ${{ experiment() == exp001 }}`.

#### Breaking changes
 - significant web backend API changes! See list of rules in docs.

#### Bug fixes
 - Fix UI code editor from being unresponsive when all the text was removed.
 - Experiment profiles won't be overwritten if providing the same filename as an existing profile.


### 24.6.10

#### Enhancements
 - we changed the "auto" algorithm for picking a good `ir_led_intensity`. We now try to maximize the intensity, up to some constraints around saturating ADCs, LED longevity, and signal. In general, we expect a higher IR intensity, but this will help with noise and detecting lower signals.
 - More improvements on the Pioreactor-specific page: added charts and a logs table.
 - Added a "retry failed tests" to the UI's self-test dialog.
 - `pio run self_test` has a new flag `--retry-failed` to only retry tests that failed in the previous run (if any).
 - better clean up when a worker is removed from a cluster.
 - reduce the mosquitto logs to reduce writes to disk and speed up connections.
 - Use lexicographical ordering for all displays of workers in the UI
 - **This only applies to new installed images, and not updates.** Updated to the latest RPI image, 2024-03-15, -> linux kernel update to 6.6. Recent versions of linux have improved support for usb wifi devices.
 - **This only applies to new installed images, and not updates.** leader-only images will install worker Python libraries.
 - **This only applies to new installed images, and not updates.** all experiment data will be deleted when the experiment is deleted.
 - performance improvements

#### Breaking changes
 - Changed the web backend API endpoints for time-series, logs, shutdown, reboot, and plugins to be more RESTful. See docs for updated rules in the docs.

#### Bug fixes
 - fix performing an "undo" when editing the config.ini and experiment profiles.
 - fix **Pioreactor v1.1** bug when change target temperature mid cycle causing the inferred temperature to change significantly.
 - if a worker disconnected from the network, messages are queued in memory until the network reconnects. This has two problems. The first is that there is a finite amount of memory, and we don't want to OOM. The second is that when the worker(s) reconnect, there is a flurry of messages. For some jobs that use messages as events, this can cause multiple triggers in quick succession. We've added some logic that helps avoid these situations:
    1. we max the queue of unsent messages to 100 (arbitrary)
    2. in important jobs, like temperature automations, it will only respond to "recent" messages and not old messages.

### 24.5.31

#### Highlights
 - New /pioreactor/`worker-name` page in the UI for a detailed view of an individual Pioreactor, including a realtime visualization of the Pioreactor!

#### Enhancements
 - UI backend now supports external MQTT broker. This configuration lives in the same place as the existing MQTT settings: in the config.ini, under `[mqtt]`.
 - Added groupings on the Experiment drop down to organize "Active" and "Inactive" experiments. An active experiment has >= 1 Pioreactor assigned to it.

#### Breaking changes
 - New log topic that partitions by the level. This should make subscribers to the log topic slimmer (like the UI, who previously would have to accept _all_ messages and filter to what they needed). Should result in a performance increase.

#### Bug fixes
 - Fix for Pioreactors page when _no workers are added to the cluster_.
 - Fix for UI labels when trying to remove labels from Pioreactors.
 - Improvements to REF self-tests.


### 24.5.22

#### Enhancements
 - Significant performance increase by using `force_turbo=1` in the Raspberry Pi. Expect a noticeable improvement in interacting with the Pioreactor. This pushes the Pi to always run "hot" (but we aren't overclocking). This does slightly increase the Pi's internal temperature, so be wary about putting the Pioreactor in very hot environment. _This settings requires a reboot to take affect._
 - adding support for changing the port and protocol of the Pioreactor UI webserver in the software. Add the following to your config.ini:
    ```
    [ui]
    port=80
    proto=http
    ```
   This doesn't _set_ the port and proto, that involves changing settings in the lighttpd configuration.

#### Bug fixes
 - more sane defaults for OD reading for v1.1 when using `auto`.
 - fix `pios plugins uninstall`
 - fix leader not correctly being identified in `pio workers status`
 - For RPi Zero W (first gen), sometimes the load_rp2040 script was failing. A new script will retry a few times. This only applies to new images.
 - fix `pio workers update-active` using the wrong HTTP verb.
 - Fix using ethernet cable to connect Pioreactor to a router: a new simple ethernet nmconnection has been added, and has higher connection priority than the PioreactorLocalLink nmconnection.
 - Fix race conditions occurring between stirring and growth-rate when they were started too quickly.

#### Known issues

 - When the local access point would start on a fresh boot, the SSID would start as `pioreactor`, and then change to `pioreactor-<leader-name>` after the next reboot.


### 24.5.13

#### Enhancements
 - UI chart legend's will support more than 8 Pioreactors.
 - UI chart colors are consistent across charts in the Overview.
 - reduce the severity of some messages, so there will be less pop-ups in the UI.
 - UI performance improvements.
   - Upgraded to React 18.3.1
   - Removed unused dependencies
 - UI's code sections use syntax-highlighting and other nicer features for editing yaml and ini files.
 - App performance improvements
   - Upgrade paho-mqtt to 2.1
   - faster `pio kill`
   - faster job start from UI
 - more humane error messages.
 - updated temperature inference model.
 - added exponentiation `**` to profile expressions. Ex: `${{ pio1:growth_rate_calculating:growth_rate.growth_rate ** 0.5 }}`
 - added `random()` to profile expressions. This returns a number between 0 and 1. Ex: `${{ 25 + 25 * random() }}`


#### Bug fixes
 - fix `pio plugins` not working on workers.
 - fix `enable_dodging_od=0` for background jobs that can dodge OD.
 - fix PWM jobs not cleaning up correctly if too many jobs try to end at the same time.
 - fix `pio kill` not returning the correct count of jobs being killed.
 - fix older Pioreactor HATs, with the ADS1115 chip, not have the method `from_voltage_to_raw_precise`.
 - fix "Manage all" not sending the correct dosing command to workers.

### 24.5.1

#### Highlights

 - initial support for Pioreactor 20ml v1.1! This is our latest iteration of Pioreactor. Even though it's a minor 0.x release, there's lots of positives about it. We encourage you to check out the upgrade kit [here](https://pioreactor.com/collections/upgrade-kits/products/pioreactor-20ml-v1-1-upgrade-kit).
 - some further support for tracking the model and version of the Pioreactor you are using. Users can change the version in the config file. For example:
   ```
   [pioreactor]
   model=pioreactor_20ml
   version=1.1
   ```
   If you have a mixed cluster (some 1.0, some 1.1), then you should put this configuration in the _unit specific_ config files.
 - For v1.1: New temperature inference algorithm makes reaching the `thermostat` setpoint quicker, and the Pioreactor can reach higher temperatures (our internal testing could easily reach up to 45C in a cool room). This algorithm uses the magic of ✨statistics✨. We may update the themostat PID values in the future, but the default ones work okay for now. A Pioreactor v1.0 update for this algorithm should come out soon, too.

 #### Enhancements

 - When using `turbidostat`, there is now a small moving average filter on the raw OD readings. This will prevent the turbidostat from firing when an OD outlier occurs.
 - MQTT data is no long persisted between leader power-cycles. This was the cause of a lot of bad UI state issues where users couldn't interact with the Pioreactor via the UI after a power-cycle (intentional or not). We originally persisted the data since we previously used MQTT as more like a database, but our engineering style has moved away from that idea, and we now only use MQTT for "ephemeral" data. Taking out the persistent MQTT data forces this style change. Users shouldn't notice anything different.
 - The leader is now the source-of-truth for the cluster's clocks. For example, when a worker boots up, it will ask the leader what the time is, and will periodically continue asking. If the leader has access to the internet, it will pull the correct time (and periodically continue asking). If the leader doesn't have access to the internet, it will use the default time on the Pi. This solves the problem of workers' clocks getting out of sync when powered down, especially in a local-access-point network.

   ![](https://i.imgur.com/vt5gxyy.png)

 - Lots of small UI improvements, including accessibility, empty-state, and loading improvements.
 - Previously, we would "kick" stirring by forcing the DC% to 100% for a moment, and then increasing the running DC% slightly. Going forward, we'll actually try the following when the
 sensor fails to read a signal: _DC% to 0%_, then _DC% to 100%_, and then a slight increase in the DC%. Why?
    - If the mixing fan has stalled, setting the DC% to 0% does nothing, since the fan is already stopped.
    - If the mixing fan is running, but the stir bar isn't in sync, this step will align the stir bar and fan again.
    - If the mixing fan is running _too fast_, but the sensor isn't reading it, this allows for a small pause.
 - The recommend way to upgrade Pioreactors and clusters is now using _release archives_. We have more control over the upgrade process this way. However, users are still welcome use the command line, `pio update`, which is what we use in house.
 - A chart legend's in the UI now displays the entire name of the worker, if there is enough room.

#### Breaking changes

 - Temporary Pioreactor labels, set in the UI, are now unique across an experiment.
 - config `max_volume_to_warn` was removed, it's now hardcoded as 90% of `max_volume_to_stop`

#### Bug fixes

 - Fix `pio ...` commands that displayed the CLI options not working on workers.
 - Potential fix for heater continuing to be on after requested to be turned off.

### 24.4.11

#### Enhancements
 - Faster app start-up performance, which should translate to faster response times.
 - Log when workers change experiment assignments.
 - Log when workers change active status.
 - Adding `[pioreactor]` section to config.inis
 - improvements to calibration charts

#### Breaking changes
 - `pio install-plugin` is now `pio plugins install`. Likewise for `uninstall`.
 - `pio list-plugins` is now `pio plugins list`.
 - `pios install-plugin` is now `pios plugins install`. Likewise for `uninstall`.

#### Bug fixes
 - fixed Log table in the UI not showing all entries.
 - fixed HAT button response in the UI.

### 24.4.3

#### Highlights

 - The Pioreactor leader can now support multiple experiments! If you have more than one Pioreactor, this change allows you to run multiple experiments simultaneously, assign Pioreactors to different experiments, and manage all experiments concurrently. No more multi-leader set ups - all you need is a single leader and multiple workers! See video [here](https://www.youtube.com/watch?v=7SuR26BQG5c).
 - Ability to delete experiments from the UI.
 - Better control over your cluster, using the Inventory page in the UI.
 - Ship with network configuration of local-link connections: plug in an ethernet from your Pioreactor to your computer, and after invoking `sudo nmcli c PioreactorLocalLink up`, you should be able to visit `http://pioreactor.local` in your browser.

 #### Enhancements
 - replace the `ip` file that is written to on startup with a new `network_info.txt` file that contains the hostname, IPv4 address, and MAC addresses.
 - Adding the ethernet (wired) mac address to the system tab.
 - new Python module for controlling workers: `pioreactor.cluster_management`
 - by default, for new installs, the local-access-point SSID is now `pioreactor_<hostname>`.
 - UI performance improvements
 - New database tables to handle workers (`workers`) and experiments assignments (`experiment_assignments`).
 - New `pio workers` CLI to mange your inventory. Try `pio workers --help` to see all the commands available.
 - Better error messages when a self-test fails.
 - `pio kill` has new options to kill specific actions. Ex: `pio kill --experiment this-exp`, `pio kill --job-source experiment_profile`


#### Breaking changes
 - When a experiment profile **stops early** (i.e. via "stop early" in the UI), it now will halt any jobs that it started. This is a change from how they worked previously, but this new behaviour is less of a surprise to users.
 - `pio add-pioreactor <name>` is now `pio workers add <name>`
 - `pio cluster-status` is now `pio workers status`
 - `utils.publish_ready_to_disconnected_state` changed names to `utils.managed_lifecycle`
 - `config.inventory` in the config.ini is no longer used. All that data is now handled in the database on the leader, and managed in the UI or CLI.
 - `pio kill <job_name>` is removed, use `pio kill --name <job_name>`.

#### Bug fixes
 - fix for not being able to access `http://pioreactor.local` reliably.
 - fix for multiple exporting datasets when selecting "All experiments"

#### Known bugs
 - removing a Pioreactor leader from an experiment will stop any experiment profiles running that are associated to that experiment.


### 24.3.10

#### Enhancements
 - For better consistency between Pioreactors, we've introduced a new configuration option that will automatically adjust the IR LED intensity to match a target value in the reference photodiode, at the start of OD reading. This means that if your IR LEDs are slightly different between Pioreactors, the IR LED output will be adjusted to match a hardcoded value. To enable this feature, change the `[od_config]` config parameter `ir_led_intensity` value to `auto`. For new installs, this is the default configuration. This _shouldn't_ change your actual OD readings very much (since we normalize raw PD by REF, and increase or decrease in REF is balanced by increase or decrease in PD), but it will make analysis easier.
 - Significant UI performance improvements: we are use less MQTT clients, which should mean faster loading, less network overhead, and overall lower resource-usage.

#### Bug fixes
 - Fixes updating automations in experiment profiles

### 24.3.4

#### Enhancements
 - reusing more MQTT clients internally => faster job startup and less network overhead

#### Bug fixes
 - using the archive upload method to update Pioreactors had a bug when distributing the archive to workers on the cluster. That has been fixed. The first time, you archive update may fail. But it should succeed the second time.
 - fix UI bug that was preventing real-time data from showing up in some custom charts.
 - fix UI bug that was causing a stale datum to appear in charts.
 - To avoid downstream permission issues, `pio` can't be run as root. That is, `sudo pio ...` will fail.
 - a typo prevented `od_config.smoothing_penalizer` from being used internally. This is fixed.
 - some retry logic for fixing "lost" state in the UI.
 - fixed numerous MQTT connections from accumulating in the UI

### 24.2.26

#### Highlights
 - **Experimental** introducing outlier filtering in growth rate calculations. This is tunable with the new `ekf_outlier_std_threshold` parameter under `[growth_rate_calculating.config]`. To turn off outlier filtering, set this parameter to some very large number (1000s). Don't put it less than 3.0 - that's silly.
 - With this new filtering, we can provide more reasonable values for the parameters of the growth rate Kalman filter. We previously had to artificially _increase_ the measurement std. deviation (`obs_std`) to allow for some outliers. This had the knock-on effect of hiding growth-rate changes, so we had to also increase that parameter `rate_std`. With better outlier protection in the model, we can move these values back. New installs will have the following parameters, and we encourage existing users to try these values if you plan to use the outlier filtering.
  ```
  [growth_rate_kalman]
  acc_std=0.0008
  obs_std=1.5
  od_std=0.0025
  rate_std=0.1
  ```
 - added configuration for alternative mqtt brokers with the new configuration
   ```
   [mqtt]
   username=pioreactor
   password=raspberry
   broker_address=
   broker_ws_port=9001
   broker_port=1883
   ws_protocol=ws
   use_tls=0
   ```

#### Enhancements
 - clear the growth-rate cache with `pio run growth_rate_cacluating clear_cache`
 - added Pioreactor specific software version to the UI: Page *Pioreactors -> Manage -> System -> Version*. **this requires a restart to display correctly**
 - new UI MQTT library. Is it faster? Maybe!
 - increased the default `max_subdose` to 1.0.

#### Bug fixes
 - fixed a case where dosing automation IO execution would not run due to a floating point rounding error.  Sorry!
 - fixed a memory leak in long running dosing automations that had thousands of dosing events.  Sorry!
 - fixed a race condition that caused an error to occur when a software PWM channel was closed too quickly.  Sorry!
 - fixed bug that was partially crashing the UI if some bad syntax was entered into a custom yaml file. Sorry!
 - fixed bug that was causing bad json from the server, causing empty / non-loading areas in the UI. Sorry!
 - fixed `datum` bug in the Overview that was crashing the UI. Sorry!


### 24.2.11
 - boot-up performance improvements
 - job start performance improvements
 - improved RPM calculation for lower RPMs.
 - Added buttons to the Overview UI to change common settings.

### 24.1.30

#### Enhancements

 - profiles in the UI are sorted by their last edit time.
 - Jobs can't run if `self_test` is running
 - exporting `pioreactor_unit_activity_data` no longer requires an experiment name to be included.
 - new config option: `samples_for_od_statistics` in `[growth_rate_calculating.config]` for specifying the number of OD samples to take for initial statistics.
 - `$` can be used in expressions (this is used to specify the `$state` setting).
 - `repeat` directive in experiment profiles.
   ```yaml
    experiment_profile_name: demo_stirring_repeat

    common:
      jobs:
        stirring:
          actions:
            - type: start
              hours_elapsed: 0.0
              options:
                target_rpm: 400.0
            - type: repeat
              hours_elapsed: 0.001
              while: ::stirring:target_rpm <= 1000
              repeat_every_hours: 12
              max_hours: 10
              actions:
                - type: update
                  hours_elapsed: 0.0
                  options:
                    target_rpm: ${{::stirring:target_rpm + 100}}
   ```
 - use expressions in `common` block. Instead of the usual `unit:job:setting` syntax, use `::job:setting`. For example:
   ```yaml
    common:
      jobs:
        stirring:
          actions:
            - type: update
              hours_elapsed: 0.002
              if: ::stirring:target_rpm > 600
              options:
                target_rpm: ${{::stirring:target_rpm - 100}}
   ```

#### Bug fixes
 - fixed a bug in the chart of OD reading that was causing historical and realtime data to be different lines.
 - fixed bug where a PWM wouldn't clean up correctly if the job was canceled too early.
 - fix for self-test `test_REF_is_in_correct_position`
 - accidentally _appended_ text to the end of an old experiment profile in the last update. We've fixed that in this update.

### 24.1.26

#### Conditionals and expressions in experiment profiles!

 - adding `if` directives to experiment_profiles, with dynamic expressions. See full docs [here](https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles#how-the-if-directive-works)

```yaml
   ...
   stirring:
     actions:
       ...
       - type: update
         hours_elapsed: 12.0
         if: pio1:od_reading:od1.od > 2.0
         options:
           - target_rpm: 600
```
 - adding dynamic options via expressions, see full docs [here](https://docs.pioreactor.com/user-guide/create-edit-experiment-profiles#expressions-in-options)

```yaml
   ...
   stirring:
     actions:
       ...
       - type: update
         hours_elapsed: 12.0
         options:
           - target_rpm: ${{ pio1:stirring:target_rpm * 1.1 }}
```


#### Breaking changes
Breaking changes to experiment profiles:
  1. the `common` block requires a `jobs` block. Previously:
     ```
     experiment_profile_name: demo_stirring_example

     metadata:
       author: Cam Davidson-Pilon
       description:

     common:
       stirring:
         actions:
           - type: start
             hours_elapsed: 0.0
             options:
               target_rpm: 400.0
     ```

     Now:
     ```
     experiment_profile_name: demo_stirring_example

     metadata:
       author: Cam Davidson-Pilon
       description:

     common:
      jobs:            # this text is required
        stirring:
          actions:
            - type: start
              hours_elapsed: 0.0
              options:
                target_rpm: 400.0
     ```
  2. `labels` has moved into the `pioreactors` block. Previously,

     ```
     experiment_profile_name: simple_stirring_example

     labels:
      worker1: PR-001

     metadata:
       author: John Doe
       description:

     pioreactors:
       worker1:
         jobs: {}
     ```

     Now,

     ```
     experiment_profile_name: simple_stirring_example

     metadata:
       author: John Doe
       description:

     pioreactors:
       worker1:
         label: PR-001
         jobs: {}
     ```

     Related, you can't use the label as an alias in the `pioreactor` block.

     Need a hand updating your profiles? Let us know, support@pioreactor.com!

 - removing `ODReadings.latest_od_reading` and it's replaced by `ODReadings.ods`.
 - removed the topic `pioreactor/{unit}/.../od_readings/od/{channel}`. Use `pioreactor/{unit}/.../od_readings/od1` or `pioreactor/{unit}/.../od_readings/od2`. This change was made to fit more and more published data into the same format (and it makes `od1` and `od2` published settings on `ODReader`)


#### Enhancements
 - `ods`, `od1`, `od2` now a published settings of `ODReadings`.
 - when a worker is first turned on, and pre-connected to a cluster, the LED is turned on to give _some_ feedback to the user.
 - using the 2023-12-11 RPi base image

#### Bug fixes
 - fixed the UI crashing if trying to edit a blank experiment profile

#### Experimental builds

We've released new 64 bit builds, and a 64 bit "headful" build. These builds are experimental, and require a RPi4, RPi5, or RPi400 due to their larger memory requirements.

  - 64 bit leader-worker and worker builds will be marginally more performant, at the cost of some additional memory consumption.
  - The "headful" leader-worker build allows you to attach a monitor, keyboard, mouse, etc. to the Raspberry Pi and use it as an interface for your cluster.

These builds are available only on our [nightly page](https://nightly.pioreactor.com).


### 24.1.12

#### Enhancements
 - optimized performance and memory consumption of experiment profiles.

#### Bug fixes
 - fix initial state of boolean switches in UI.
 - fix Raspberry Pi 5 not addressing PWMs correctly.

### 24.1.9

#### Enhancements
 - Initial support for RPi5! To use an RPi5, we recommend not upgrading the software, but using a fresh image install. Under the hood:
   - we are using a new route to load the firmware on the HATs RP2040 (using `linuxgpio`)
   - the hardware PWMs on the RPi5 use a different chip location. This required a new `rpi_hardware_pwm` release.
 - new ENV variable, `HAT_PRESENT=1`, can be set to skip `is_HAT_present` checks.
 - added the RPis unique MAC addresses to the `Manage -> System` tab on the Pioreactors page.
 - added table `ir_led_intensities` to be able to be exported on the Exports page.
 - added a new `smoothing_penalizer` config option to `[od_config]`. This parameter, which has default value 700, controls how much smoothing to apply to optical density measurements. This smoothing has always been applied, but now it's a config option.
 - Cleaned up some UI interactions

#### Breaking changes
 - `PWM` class is no longer initialized with a `duty_cycle`, instead:
 - `PWM` class must be started with `start(initial_duty_cyle)`
 - moved `get_rpi_machine` to `pioreactor.version`

#### Bug fixes
 - Ack! I reintroduced a UI export bug. Fix is present going forward. For existing users, try the following: https://forum.pioreactor.com/t/new-pioreactor-release-23-11-18/179/2
 - fixed a bug where stirring DC would jump up too high when RPM measured 0.


### 23.12.11

#### Enhancements

 - Improvements to OD calibration and pump calibrations. Both now have a `-f` option to provide a json file with calibration data, to skip rerunning data-gathering routines. For example: `pio run pump_calibration -f pump_data.json`.
 - Ability to update via our release_archives (available on the [Github release page](https://github.com/Pioreactor/pioreactor/releases)) via the UI. To turn this feature off (which is a recommended practice when you expose your UI publicly), add an empty file called `DISALLOW_UI_UPLOADS` to the `~/.pioreactor` directory.
 - A new config option to change the max volume to dose when a larger dose volume is split. For example, if your chemostat asks to dose 1.6 ml, our internal algorithm will dose 0.75, 0.75 and 0.1 (this is to avoid overflow). The 0.75 was previously hardcoded, but is now a config `max_subdose` under section `[dosing_automation.config]` (default is still 0.75 ml).

#### Breaking changes

 - Changes to `types.DosingProgram`, now it requires an MQTT client. Usually this is `automation.pub_client`. This is to avoid a memory leak!

#### Bug fixes

 - Fixed an problem where an automation would not successfully end due to it being "blocked" by a `while` loop in the `execute`.
 - Fixed a memory leak in dosing control when the automation would pump many many times.

### 23.11.29

 - fix for exporting data from the UI

### 23.11.28

#### Breaking changes
 - Merged the turbidostat automations into one. You can either select to target nOD or target OD, but not both!
 - `ws_url` in the configuration now requires a fully qualified url. Example: `ws://...` or `wss://...`.
 - Removed `morbidostat` dosing automation, users should try to use pid_morbidostat. The morbidostat code is still available to be added as a custom plugin here: https://github.com/Pioreactor/automation-examples/blob/main/dosing/morbidostat.py
 - Removed `constant_duty_cycle` temperature automation. Again, the code is available here: https://github.com/Pioreactor/automation-examples/blob/main/temperature/constant_duty_cycle.py
 - `pid_morbidostat` now explicitly uses the keyword arg `target_normalized_od`, instead of `target_od`. It always has been nOD.

#### Enhancements
 - Both "Target OD" and "Target nOD" displayed and editable in the UI.
 - Previously, if the LED channel was locked (most common when OD reading was running), then any changes to the LED intensity (via the UI) would be silently rejected. This is changed: we have added retry logic that will attempt to keep changing it a few more times (hopefully to avoid the lock)
 - Added some light form validation in the automations dialog in the UI.
 - New environment variable to skip loading plugins, `SKIP_PLUGINS`. Useful for debugging. Ex:
   ```
   SKIP_PLUGINS=1 pio run stirring
   ```
 - elements in the `field` array in automation yamls now can include a `type` option (`numeric` or `string` for now). Default is `numeric` if not specified.

#### Bug Fixes
 - Fix experiment profile validation error
 - The "Stop" button is always available now in the "Dosing" tab for "Manage all Pioreactors".
 - Fix for Ngrok remote access.
 - Fixed a race condition between starting an automation and not getting OD data in time.
 - The automation form in the UI for pid_morbidostat was missing `volume`, that's been added now.


### 23.11.18
 - No more waiting around for growth-rate-calculating to get to "Ready" state
 - The "Label" step in the New Experiment flow is skipped if there is only 1 active Pioreactor in the cluster.
 - Silenced the "LED is locked" warning - now it's a DEBUG level message.
 - Fixed bug that wasn't passing lists correctly  in `TopicToParserToTable`
 - Faster boot times.
 - Faster UI load times by gzip-ing assets.
 - Fixed a bug where a plugin would not be loaded if it's name collided with a module in the stdlib. For example, putting `test.py` in `.pioreactor/plugins` would not be loaded, since when we tried to import `test`, it would load the stdlib's `test`, not the local plugin. This has been fixed.
 - Simplify some UI elements.
 - Security improvements.
 - Reduce the default LED intensity in `light_dark_cycle` from 50% to 5%. This is more appropriate for sparse cultures.
 - Fixed a race condition when starting a hotspot with boot config.ini.
 - changed how `is_HAT_present` determine is the HAT is on the Pi. Previously, it used the i2c bus to check if the RP2040's firmware was active. This would fail if the HAT was present, but the firmware or i2c wasn't working. Now we check the EEPROM, which is a much more robust test.

### 23.11.08

 - fix bug in `timeout` in `Stirrer.block_until_rpm_is_close_to_target` that wasn't using time correctly.
 - Workers can now also be the local-access-point (aka the "router" in a network). Previously only leaders could.
 - Experiment profiles now support a `log` directive with some dynamic templating:
   ```
      - type: log
        hours_elapsed: 0.025
        options:
          message: "{job} increasing to 800 RPM" # alerts the message: "stirring increasing to 800 RPM"
   ```
   See full example [here](https://github.com/Pioreactor/experiment_profile_examples/blob/main/08_logging.yaml).
 - Experiment profiles now supports changing LEDs like any other job (i.e. they can use `start`, `update` and `stop` directives). See example [here](https://github.com/Pioreactor/experiment_profile_examples/blob/main/03_dosing_and_leds.yaml).
 - Experiment profile clean up. I think there are less bugs!
 - `pio clear_cache` now has an `as_int` option to look for ints - useful when clearing caches with ints as keys.
 - fix issue where if an extra config.ini was provided in the /boot dir before a worker startup, adding the worker to a cluster would fail due to a permission issue.
 - potential fix for RPi 3B and RPi Zeros not connecting to hotspots: change the `proto` to `wpa` in your config.ini on the Pioreactor with the local-access-point, and restart that Pioreactor. You config.ini should look like:

   ```
   [local_access_point]
   ssid=pioreactor
   passphrase=raspberry
   proto=wpa
   ```

   **Changing to WPA does weaken the security however! It's easier for unwanted users to get onto this wifi.**

   A more robust solution is in the works for RPi 3B and Zeros.

 - Slight change to the API initialization of ADCReader. Take a look if you were using that class.



### 23.10.23

#### Bookworm release!

The Raspberry Pi Foundation provides new operating system every few years (built off of Debian's work). Earlier this month, they released RPi OS Bookworm. There are lots of nice changes, but the important details for us:

 - New Python version
 - New GPIO libraries
 - New local-access-point improvements

**We strongly recommend you upgrade to this release. However, upgrading to this new operating system requires a full SD rewrite. See steps below on how to preserve and transfer your data**.


#### Optimizations

With some other optimizations, we have significantly improved the performance and responsiveness of the Pioreactor software. You should notice things will feel snappier! For example, the command-line responsiveness is about 33% faster, which means actions from the the UI will start faster. Because of this new performance, we can even squeeze some more data into our algorithms and get improved accuracy.

Along with Python being faster, our database is also faster now => faster inserts, UI graphs, and data exports.


#### Export and import your existing data into a new image

Note: you don't _need_ to do this. This is only if you want to move existing data to the new Pioreactor.

See instructions [here](https://docs.pioreactor.com/user-guide/export-import-existing-data).


#### Full Changelog

 - Replaced `RPi.GPIO` with `lgpio`
 - Python 3.9 is replaced by 3.11
 - Ability to choose the x-axis scale in the UI Overview: clock time, or elapsed time. Use (or add) `time_display_mode` under section `[ui.overview.settings]`, with values `clock_time` or `hours` respectively.
 - Fixed bug that was not clearing OD blanks from the UI
 - dropped RaspAP for a native solution. The native solution is much simpler, and should show up faster than our RaspAP solution.
  - If your leader Raspberry Pi has an ethernet port, you can connect this into an internet-accessible router and give your cluster access to the internet!
 - Updated lots of our Python dependencies
 - Improved start up time by hiding dependencies
 - Added database table to track experiment profile starts.


### 23.10.12

#### Bug fixes
 - Web server was crashing on start! Solution was to upgrade flask.

### 23.10.10

#### Bug fixes

 - Fix bug that wasn't allowing for manual dosing / LED updates.
 - Fix bug that was disconnecting workers with using "stop all activity" in the UI when pumps were running.

#### Enhancements

 - `pios update` now has a `--source` parameter.

### 23.10.5

#### Bug fixes

 - Fix an OD calibration bug that would produce an extremely high value when the signal was below the minimum signal (the blank) during OD calibration.
 - IPv4 is really IPv4 now.

#### Enhancements

 - Adding ability to install plugins by name via the UI.
 - New tools to update Pioreactors on a local access point. More docs coming soon!
 - New `turbidostat_targeting_od` dosing automation. This is just like the existing `turbidostat`, but
targets the raw OD instead of normalized OD. This is most useful post-OD calibration.
 - In the UI, the dosing automation "Turbidostat" has been renamed "Turbidostat Targeting nOD"


### 23.9.20
The previous change:

>  - Base automations now subclass from `pioreactor.automations.BaseAutomationJob`. You may need to change custom automation imports from, for example, `from pioreactor.automations import DosingAutomationJobContrib` to `from pioreactor.automations.dosing.base import DosingAutomationJobContrib`

had an import error that we didn't see in testing. We changed this to:

 - Base automations now subclass from `pioreactor.automations.base.AutomationJob`.
 - Fix bug on /updates page.

### 23.9.19
 - When installing plugins, any leader-only commands would not be run. This is fixed.
 - Base automations now subclass from `pioreactor.automations.BaseAutomationJob`. You may need to change custom automation imports from, for example, `from pioreactor.automations import DosingAutomationJobContrib` to `from pioreactor.automations.dosing.base import DosingAutomationJobContrib`
 - Fixed bug that ignored `.yml` files in the UI.
 - Improvements to experiment profiles, both in the UI and in the backend. Executing now verifies common mistakes in experiment profiles before it runs.
 - Fixed a bug that could cause controllers to have a disconnected automation. #422
 - SPI is on by default on all new image installs
 - Plugin author information is presented on the `/plugins` page in the UI.

### 23.8.29
 - Pioreactor's IPv4 and hostname is now displayed under System in the UI.
 - In configuration, renamed section `dosing_automation` to `dosing_automation.config` (only applies to new installs). It's recommended for existing users to make this change, too.
 - new safety check that will stop automated dosing if vial liquid volume is above 18ml during dosing. This can be changed with `max_volume_to_stop` under `[dosing_automation.config]`
 - New configuration option `waste_removal_multiplier` to run the waste pump for a different multiplier (default 2), under `[dosing_automation.config]`
 - A warning will appear if the reference PD is measuring too much noise.
 - added another self-test test to confirm that an aturbid liquid in vial will produce a near 0 signal.
 - general improvements to self-test
 - New CLI command: `pio clear-cache <cache> <key>` to remove a key from a cache.
 - New CLI subcommand `delete` of `pio run od_blank` to remove the current experiment's blank values. This is also exposed in the UI.

### 23.7.31

 - Using builtin PID controller logic, instead of a 3rd party library. This shouldn't require any updates to PID code or parameters.
 - Better error handling when the PioreactorUI API can't be reached.
 - Some initial support for Basic Auth in the PioreactorUI
 - improved sensitivity of self-test `test_REF_is_in_correct_position`.
 - executing experiment profiles now checks for required plugins.
 - `pio rm` now asks for confirmation before executing.
 - Some minor noise reduction in OD reading job.
 - Plugins can be built with a flag file LEADER_ONLY to only be installed on the leader Pioreactor.
 - Stirring now pauses and restart during OD calibration. Thanks @odcambc!
 - **Breaking**: Light/Dark cycle LED automation uses minutes instead of hours now! Thanks @c-bun!


### 23.6.27

#### Highlights
 - The UI now offers a way to upgrade to the bleeding-edge Pioreactor app and UI software, called "development". This software is unstable (and fun!).

#### Better thermostat

 - Improved temperature inference accuracy.
 - After some testing, we've found that the following set of PID parameters for `temperature_automation.thermostat` works better¹ than the previous set of parameters:
```
Kp=3.0
Ki=0.0
Kd=4.5
```

This set now ships with all new installations of Pioreactor software. **Existing users can update their parameters in the config.ini**

¹ Better == less thermal runaways, less sensitive to shocks, similar overshoot and settling time.

#### Everything else
 - On startup, the Raspberry Pi will write its IP address to a text file `/boot/ip`. This means that if you (carefully) remove the SD card, you should be able see the IP address (hopefully it hasn't changed).
 - Fixed `source` in `BackgroundJobContrib` - thanks @odcambc!
 - `pio add-pioreactor` will now accept an option that is the password of the RPi being added (default: `raspberry`). Ex: `pio add-pioreactor worker1 -p mypass`
 - Improved some warning and error messages.
 - Improved watchdog detecting and fixing "lost" Pioreactors.
 - Starting to test software against Python 3.11, in anticipation of a Python 3.11 coming to Raspberry Pi OS.
 - Improvements to bash scripts to make them more robust.
 - Adding `pios rm <filepath>` to remove a file across the cluster.
 - Adding `-r` option to `pio update`. Example: `pio update <x> -r <repo>` to install from a repo (default is Pioreactor's repos).
 - `structs.ODCalibration` has a new schema, `inferred_od600s` is now `od600s`. See `pioreactor.structs`.

### 23.6.7

#### Highlights
 - Support for viewing, starting and stopping _experiment profiles_ in the UI!
 - Adding manual dosing adjustment form under Dosing tab in the UI!

#### Everything else
 - New API for experiment profiles: `pio run experiment_profile`, with subcommands `execute` and `verify`. So what use to be `pio run execute_experiment_profile <filename>` is now: `pio run experiment_profile execute <filename>`. The `verify` subcommand is for checking the yaml file for errors.
 - new leader CLI command: `pios cp <filepath>` will move a file on your leader to the entire cluster. This is useful for distributing plugins and Python wheels across your workers.
 - plugins can now add `post_install.sh` and `pre_uninstall.sh` bash scripts.
 - added `[stirring]` option `duration_between_updates_seconds` to config, default is 23.0.
 - PIDMorbidostat has a configuration parameter `[dosing_automation.pid_morbidostat].minimum_dosing_volume_ml` (default 0.1). If a calculated volume to be dosed is less than this parameter, then it's set to 0.0 instead.
 - adding `--manually` flag to pump actions, ex: `pio run add_media --ml 1 --manually`. This _doesn't_ run the pump, but still fires a dosing event, which downstream jobs listen to (ex: saves to database, will update metrics). See next change:

### 23.5.16
 - UX improvements to `pio run pump_calibration`
 - `monitor` is more robust, so as to give users better access to information instead of hard-failing.
 - `monitor` now checks for access to web service
 - `monitor` now checks the voltage on the PWM rail and will alert if falls to much. If not using the an AUX power supply, this is directly tied to the RPi's power supply.
 - `monitor` also publishes the read voltage as a published setting. This is available in the /pioreactor card under System in the UI.
 - sqlite3worker is now vendored in the core app. This means we can publish on PyPI.
 - improved `systemctl` start up.
 - added `[dosing_automation]` section to config.ini (existing users will have to add this manually), with an option `pause_between_subdoses_seconds` to control how long to wait between sub doses (these are the smaller doses that make up a larger dose, i.e. 0.5ml + 0.5ml = 1.0ml). Default is 5 seconds

#### Beta feature: Pioreactor experiment profiles

Also shipping this version is early support for experiment profiles. What are they? They are "scripts" that will start, stop, pause, resume, update jobs and actions without user interaction. They are defined with a yaml file, according to the following spec (subject to change):

For examples of yaml files, see the repo: https://github.com/Pioreactor/experiment_profile_examples

To use a profile, save the yaml file to your leader Pioreactor. Run it with `pio run execute_experiment_profile <path_to_yaml>`. Note that killing the `execute_experiment_profile` will only stop execution of upcoming actions, and won't stop any jobs that have already started from the profile.


### 23.4.28
 - improved detection of under-voltage, and power supply problems.
 - pumps will halt if a MQTT disconnect occurs. This is to prevent the edge case when pumps are running on a worker, but not controllable from the UI due to an MQTT disconnect.
 - improvements to backing up the SQLite3 database.
 - improvements to self-test "Reference photodiode is correct magnitude"

#### Bug fixes
 - fix bug in `pio run od_calibration list`

### 23.4.14

 - `pio update app` will default to installing the succeeding release of Pioreactor app, which may or may not be the latest. This is to ensure that no update script is skipped.
 - Added new "Past Experiments" page
 - Fix for "Reference photodiode is correct magnitude" self-test.

### 23.4.4
 - Job growth_rate_calculating will dynamically choose initial values for its internal statistics.
 - New entry in `stirring` section in config.ini: `use_rpm` (a boolean) can be used to engage or disengage the closed loop RPM system.
 - Calibration structs change `timestamp` -> `created_at`.
 - Backend work to complete calibrations utilities:
   - Edits to the `calibrations` table in the database require a full drop and recreation.
   - New API endpoints on the webserver to store calibrations, get calibrations, set as current, etc.
   - New CLI: `pio run <x>_calibration publish` will publish a calibration to the webserver

### 23.3.21
 - Python files in `plugins/` folder on leader are viewable on the /plugins page in the UI.
 - Python files in `plugins/` folder on leader are uninstallable (aka deleted) on the /plugins page in the UI.
 - `pio uninstall-plugin` will delete Python plugins in the .pioreactor/plugins/ dir if provided the _python file name_, sans `.py`.
 - `pios reboot` should now work for the leader.
 - Using the Pioreactor with an ethernet connection will provide the correct ip address.

### 23.3.16
 - files in `~/.pioreactor/plugins` are now loaded lexographically. Previously it was up the the filesystem.
 - Performance improvements for PioreactorUI
 - Added new indexes to the SQLite database to improve read performance. This change will only impact new installs of Pioreactor.
 - Improvements in error handling when plugins can't load.

#### Bug fixes
 - fixed bug in adding new pioreactor not passing an avahi check.

### 23.3.9
 - Removed the scaling difference between hardware versions in OD Reading.
 - Moving some Python dependencies into this repo.
 - More error handling around hardware versions
 - fix `self_test.test_ambient_light_interference` test failing for HAT 1.1.

### 23.3.2
 - fix bug in ending experiments not cleaning up automations properly.

### 23.3.1

 - Performance improvements
 - Python dependencies for Pioreactor UI are now handled by this project.
 - Better initialization of jobs from UI
 - Version information now presented in UI
 - More support for HAT version 1.1
 - more Linux permission updates.
 - Refactor internal pumping code. There's more flexibility that allows for solving parts of #384. Including:
  - creating cleaning scripts
  - creating cycling scripts, that also respect the rates of specific pumps vs waste (so that you don't overflow if addition rate > removal rate)
  - Namely, new functions `circulate_media` and `circulate_alt_media` are introduced that will cycle both a pump and the waste pump simultaneously. The waste pump starts first and ends second.
 - removed the dosing automation `continuous cycling`. It was redundant, and a leftover from an old feature.

#### Bug fixes
 - Fixed `pio kill <job>` to actually kill a job
 - Fix for running PID morbidostat

### 23.2.17

#### Bug fixes

 - Fix "End experiment" killing all jobs.
 - Fix `pio view-cache` not working outside the home directory.
 - Fixes for hardware HAT version 1.1.
 - `led_intensity` cleans itself up better.


### 23.2.8

#### Bug fixes

 - Fix error in growth rate calculating job that prevented it from starting.


### 23.2.6

#### New features
 - Watchdog job now listens for new workers that join the network and are not part of the cluster. A NOTICE message is logged and sent to the UI.
 - Initial _API_ support for adding more pumps to the Pioreactor. See docs [here](https://docs.pioreactor.com/developer-guide/writing-pump-software).
 - Time series charts are now able to be added the the UI via `contrib` folders. Put a yaml file under `~/.pioreactor/plugins/ui/contrib/charts`. See examples [here](https://github.com/Pioreactor/pioreactorui/tree/master/contrib/charts).
 - New roll-up table available to be exported from the UI: Pioreactor unit activity data roll-up. This is a rolled-up of Pioreactor unit activity data rolled up to every minute, so it should be about one order of magnitude less data versus the original table.

#### API changes

 - Pioreactor UI has a more RESTful API, so some internal urls have changed. See full new API [here](https://docs.pioreactor.com/developer-guide/web-ui-api). UI version >= 23.2.0 required.
 - `SummableList` is replaced with `SummableDict`
 - `execute_io_action` returns a dictionary now (instead of a list).
 - Config: Removed `daily_growth_rate` from `[ui.overview.settings]`
 - Config: Added `implied_daily_growth_rate` under `[ui.overview.charts]`
 - Dropped `pio run-always`. Jobs just use `pio run` now.


### 23.1.3
 - Fix `dosing_events` table not be populated caused by an incorrect SQLite3 trigger.
 - Running a pump _continuously_ will produce MQTT events with new timestamps (previously it was the same timestamp.)
 - Faster loading for some pages in Pioreactor UI
 - Fix for RaspAP not turning on when requested using `local_access_point` file
 - Caching in Pioreactor UI is improved.
 - systemd services should boot in an _even_ better order
 - Bug fixes
 - New 64bit images are available on the CustoPiZer release page. Default is still 32bit until more testing can be done.

### 23.1.2
 - fix `pio update` bugs
 - new config for `[logging]` section, `console_log_level` which control which level of logging to show on the command line (does not effect logs in the database, or disk)
 - systemd services should boot in a better order
 - the latest experiment from the database is always the most recently inserted experiment, ignoring the created_at column (i.e. we use ROWID). This is to avoid cases where users change times (or use a local access point).
 - Fixes for `fraction_of_volume_that_is_alternative_media` chart in the UI

### 23.1.1
 - fix `pio update` bugs

### 23.1.0
 - early support for HATs with Pico hardware
 - new modules `pioreactor.util.adcs` and `pioreactor.utils.dacs` to abstract DACs and ADCs.
 - `pio update` has a new api: `pio update app <options>`, `pio update ui <options>`.
 - added version of UI & firmware to `pio version -v`
 - PioreactorUI has a different way to update, rather than using git. We now version the PioreactorUI, so it's easier to know if which version is being used.
 - `pio update app` now has a `--version` option to specify a version of the Pioreactor software.
 - `pio update ui` now has a `--version` option to specify a version of the Pioreactor UI.
 - power-saving improvements
 - image size optimizations
 - simplify logging, and avoid an eventual recursion error.
 - `source` in logging events is now correct.
 - experiment data is no longer published to MQTT. The source of truth is the db, via the web API.
 - correctly publish `alt_media_fraction` to MQTT in dosing jobs
 - dosing automations now keep track of vial volume, as attribute `vial_volume`. This is also published to MQTT.
 - corrections to how `alt_media_fraction` is calculated. It no longer assumes constant vial size, which was
   producing slightly incorrect results.
 - `execute_io_action` has been changed to add the same ratio of media and alt_media before removing liquid. This satisfies:
   1. If users asks to dose X, X will be dosed.
   2. Ratio between media and alt_media is constant between remove_waste actions.
   3. Not more than Y volume is added before liquid is removed.
   The catch is that if there is a lot of volume of one being added, and only a little of another, it's possible
   that accuracy of the latter one will be affected.
 - users can now provide the initial ratio of media to alt_media (not yet from the UI or config.ini).
 - users can specify, in their config.ini under section `bioreactor`, values `max_volume_ml` and `initial_volume_ml`. The former is used to provide the stable limit of volume (i.e. the position of the outflow tube determines this). The latter is how much volume is in the bioreactor initially. This is useful for users who wish to add medias manually.

### 22.12.3
 - fix for chemostat

### 22.12.2
 - Remove some errant debugging statements
 - Reduce MQTT's load on the leader by tuning the keepalive interval to something larger (for less sensitive connections).
 - `pio reboot` will now work on leader, but will happen last.
 - More strict msgspec Structs
 - fix od_blank error
 - Added a last will to actions that will fire if the action disconnects ungracefully.
 - Better handling of LED flashing from error codes.

### 22.12.1
 - Support latest HAT version 1.0
 - Serial number is available under `pioreactor.version.serial_number`
 - Serial number is also printed with `pio version -v`

### 22.12.0
 - Fixed config.ini not being update in the UI.
 - Fixed bug in adding worker to cluster
 - `pio add-pioreactor` now returns an error signal if the addition failed.
 - remove testing data from being added to database

### 22.11.7
 - Improvements to UI
 - Fix bug in leader's firstboot.sh
 - Fix bug when temperature is changed too quickly in `thermostat`

### 22.11.6
 - PWM DC% changes are logged to MQTT under `pioreactor/<unit>/<exp>/pwms/dc` as a JSON value (similar to LED intensities).
 - The pioreactor cards in the UI display the PWM DC %.
 - user defined callbacks in ODReader have changed to be bound methods on the class (hence, you
 can use `self` in the callback.)
 - New SQL table `pwm_dcs`.
 - Performance improvements to the UI
 - Adding authentication on mosquitto, the MQTT broker running on leader.

### 22.11.5
 - Replace dbm with disk-cache in core. Benefits: makes storing types easier, comparable performance to dbm, promises of process-safety and thread-safety, align all datastores to sqlite3.
 - Some caching in the UI now for common API calls.
 - Improvements to UI

### 22.11.4
 - Fixes for UI
 - Smoother transitions in UI
 - new ENV variable `LOCAL_ACCESS_POINT` that represents if local access point is online


### 22.11.3
 - Fix bug in UI that wasn't letting users update software
 - during `pio update --app`, we now check for additional files in the github release that are to be executed. This provides a path of upgrading non-Python things.
 - Improvements to PioreactorUI


### 22.11.2
 - Removing `parent` from BackgroundSubJob
 - Make thermostat heuristic slightly better
 - fix bug in OD Calibration
 - If the ADC has an offset (due to hardware, or ambient light), it will now be removed from all inputs before being processed in OD Readings.

### 22.11.1
 - Fix bug where users are not able to start a job.
 - Revisit pump and od calibrations. Some changes to the CLI.
 - Some improvements to stirring calibration.
 - Fix stirring calibration not responding in the UI
 - Fix uninstall plugin bug
 - Fix booleans not showing correctly in the PioreactorUI

### 22.10.4
 - removed the dbm storage `pio_jobs_running`. Instead, each job will write metadata about its currently running state to the (tmp) file `job_metadata_<job_name>`. This fixes issue #350.
 - Fixed UI issue where specific configs weren't being saved.

### 22.10.3
 - no-op release

### 22.10.2
 - no-op release

### 22.10.1
 - `BackgroundJobWithDodging` now looks for the config.ini section `[<job_name>.config]`.

### 22.10.0
 - New API for adding SQL tables via plugins, and for registering MQTT -> DB parsers.
 - New topic for experiment name in MQTT: `pioreactor/latest_experiment/experiment`.
 - New topic for experiment timestamp in MQTT: `pioreactor/latest_experiment/created_at`.
 - `stable` renamed to `thermostat`
 - new callback API for pushing the HAT button down, see `Monitor` class.

### 22.9.6
 - improve reliability of self-test `test_REF_is_in_correct_position`
 - improve the early OD reading signal behaviour.
 - new API on jobs for `job_name` (class level now)

### 22.9.5
 - The SQL triggers were not added to the images, so `pioreactor_unit_activity_data` was never populated. This is fixed.
 - New web server backend. Went from js/Node to python (Flask)/lighttp.
 - Export datasets now cleans up its csvs.

### 22.9.4
 - Bug fixes

### 22.9.3
 - temperature automation `silent` is now `only_record_temperature`.
 - using new official RPi image from 2022-09-06 as a source image.
 - Bug fixes

### 22.9.2
 - added subcommands `display_current`, `change_current`, `list` to pump calibration
 - Pump calibration follows the same format as LED calibrations. Current calibrations can be replaced with previous.
 - Adding calibration curves to calibrations' `display_current`
 - `pio run export_experiment_data` now has an flag argument to partition csvs by unit.
 - pump calibrations are now keyed by `media`, `waste`, `alt_media` in storage `current_pump_calibrations`
 - Dosing automation have access to `latest_od` now.
 - Bump plotext.


### 22.9.1
 - `local_ac_hz` is now optional
 - maybe fix bugs for local AP
 - add retries for button detection


###  22.9.0
 - Stirring now has the ability to restart itself if it detects it has stalled.
 - od_normalization has been removed. Instead, there is a small routine `od_statistics` that is called by both `od_blank` and `growth_rate_calculating`. The latter also now stores the required od statistics to storage (previous it was the `od_normalization` job).
 - The LEDs in the pioreactor have been moved up 0.5mm.
 - Error-handling and user improvements to `pump_calibration`.
 - `pid_turbidostat` was removed, replaced with the simpler `turbidostat`.
 - Adding new table `pioreactor_unit_activity_data` that makes analysis much easier.
 - Adding new table `calibrations`.
 - New action `od_calibration` that easily allows you to add an OD600 calibration to your pioreactor. See docs: https://docs.pioreactor.com/user-guide/calibrate-od600
 - _paramiko_ library is no longer a dependency
 - in `growth_rate_calculating` job, `kalman_filter_outputs` is now included in `published_settings`
 - Fix bug that wasn't saving automation events to the database.
 - new function `voltage_in_aux` that measures what voltage is in the AUX.
 - `od_readings_raw` db table renamed to `od_readings`
 - `od_readings_raw.od_reading_v` renamed to `od_readings`
 - Changes to `structs.ODReadings` and `structs.ODReading`
 - Changes to where job `od_reading` publishes data in MQTT: now `.../od_reading/ods/` and `.../od_reading/od/<channel>`
 - Rename `latest_od` property in all automations to `latest_normalized_od`. Later we will introduce `latest_od` which refers to data directly from od_reading job.
 - `turbidostat` automation now accepts `target_normalized_od` instead of `target_od`. Likewise for `pid_morbidostat`.
 - new config option under `od_config`: `use_calibration` is a boolean to ask the od_reading job to use the current calibration or not.
 - `PIDTurbidostat` automation has been nuked completely.
 - New base background job, `BackgroundJobWithDodging`, that makes it easy to change an action during od reading

### 22.7.0
 - Subtle changes to how jobs disconnect and clean up. `job.set_state("disconnected")` won't clean up connections to loggers, MQTT, etc, but will signal to the app that it's no longer available to use.
 - In `config.ini`, `ir_intensity` -> `ir_led_intensity`
 - caches that keep state (like `led_locks`) now use absence and presence to determine state, instead of specific value in the cache.
 - `network.inventory` -> `cluster.inventory`
 - `network.topology` -> `cluster.topology`
 - sql table `experiments.timestamp` ->  `experiments.created_at`
 - sql table `pioreactor_unit_labels` has new column `created_at`
 - Added `TMPDIR` the env variables, which points to `/tmp/`
 - Aided development on Windows machines
 - Added new LED automation: `light_dark_cycle`. This allows for LEDs to follow a day/night cycle, at a specific LED intensity.
 - Leader now accesses other machines always using the `.local` TLD.
 - New config option `local_ac_hz`
 - New self-test routine that checks if the REF is in the correct PD channel.
 - IR REF now uses a moving average of the first few values, instead of only the initial value. This produces much more accurate normalization values.



### 22.6.0
 - You can now edit the config.ini without having to boot a Pioreactor. By adding a file called `config.ini` to the `boot` folder when the SD card is interested in a computer, the `/boot/config.ini` will be merged with the Pioreactor's `config.ini`. This is useful for changing settings before ever starting up your Pioreactor for the first time. See below.
 - `config.ini` is now the place where the local-access-point's SSID and passphrase are stored.
 - new `pio` command on leader: `pio discover-workers` returns a list of workers on the network (may be a superset of `inventory` in the config.ini)
 - new `pios` command on leader: `pios reboot`. Reboots all active workers in the cluster.
 - self-test tests run in parallel
 - Adding `NOTICE` log level, which will appear in the UI.
 - New schemas for `kalman_filter_outputs` and `od_blanks` tables in the db.

### 22.4.3
 - table `led_events` is renamed to `led_change_events`
 - automation events returned from `execute` are published to MQTT under the published setting `latest_event`
 - new tables `led_automation_events`, `dosing_automation_events`, `temperature_automation_events`
 - `pioreactor.automation.events.Event` renamed to `pioreactor.automation.events.AutomationEvent`. The have a second kwarg that accepts a dict of data (must be json-serializable).
 - new leader command `pios reboot`: reboot RPis on the network, optionally specific ones with `--unit` flag.
 - new CLI tool: `pio log -m <message>` which will post a message to the pioreactors logs (everywhere). Example: this is used internally after systemd finish to log to our system.

### 22.4.2
 - Added ability to add callbacks to ODReader. See `add_pre_read_callback` and `add_post_read_callback`.
 - Fix bug associated with user changes.
 - `pio logs` no longer uses MQTT. Also, it now prints their entire log file.
 - BETA: testing shipping with access-point capabilities. See docs.

### 22.4.1
 - Fix bug associated with user changes.

### 22.4.0
 - store more experiment metadata, like strain and media, in the database.
 - adding temporary labels of Pioreactors into the database in `pioreactor_unit_labels` table
 - renaming some tables, `alt_media_fraction` -> `alt_media_fractions`, `ir_led_intensity` -> `ir_led_intensities`
 - pumps now throw a `CalibrationError` exception if their calibration is not defined.
 - default user is no longer `pi`. It is now `pioreactor`. Any coded paths like `/home/pi/` should be updated to `home/pioreactor/`.
 - new image metadata file added to `home/pioreactor/.pioreactor/.image_metadata`


### 22.3.0
 - fixed memory leak in MQTT connections
 - better clean up after a job disconnects
 - If the temperature of the heating PCB gets too high, the automation switches to Silent (previously it did not switch at all.)
 - "datatype" field in `published_settings` is now used to cast before being given to `set_*` methods.
 - Internally, the repo uses the `msgspec` library for complex MQTT message validation. This also introduces the `pioreactor.structs` module which details the structure of the messages.
 - Name change: `DosingAutomation` -> `DosingAutomationJob`, `TemperatureAutomation` -> `TemperatureAutomationJob`, `LEDAutomation` -> `LEDAutomationJob`.
 - New json-encoded datatype for changing automations over MQTT: see `pioreactor.struct.Automation`
 - `pio run led_intensity` has new API: use the flags, ex: `--A 10.0`, to set the intensities on different channels.
 - `pioreactor.actions.led_intensity` has a new API that accepts the desired state as a dict.
 - pump actions are now under `pioreactor.actions.pump` instead of their own files.

### 22.2.0
 - Added more error codes for the ADC, network issues, and high temperature
 - Reduce chance of running multiple growth_rate_calculating jobs
 - Custom exceptions thrown in the Python software.
 - New checks for HAT being present, and Heating PCB being present, before a job is run (if required in the job).
 - QOL improvements to stirring calibration
 - Calibrations now store the data locally, alongside the calibration results, in the local storage.
 - New API in `DosingController` to add custom pumps
 - Some `job_name`s are disallowed to avoid MQTT conflicts
 - ADCReader now will estimate the local AC hertz to get a better OD reading signal.
 - Custom Python exceptions were introduced.
 - `pioreactor.hardware_mappings` is renamed to `pioreactor.hardware`
 - New `is_HAT_present` and `is_heating_pcb_present` functions
 - ErrorCodes is gone - use global variables in error_codes
 - Adding logic for 180° sensor to growth_rate_calculating
 - Pumps now have a state broadcast to MQTT, and thus can be "disconnected" over MQTT.
 - Improved the response time of stopping pumps from the web UI.


### 22.1.0
 - improved temperature-recording frequency (10m to 4m)
 - removed the PWM's DC maximum on the heating output.
 - New `pioreactor.version.hardware_verion` which reads from the HAT's EEPROM which version
   of board is being used.
 - removed PD channels 3 & 4.
 - `angle` column in `od_readings_raw` table in database is now an integer.



### 21.12.0
 - `pid_stable` automation renamed to `stable`
 - jobs can now publish to `pioreactor/<unit>/+/monitor/flicker_led_with_error_code/<error code>`
    to have the LED flash a specific error code.
 - fixed errors raised when not able to connect to leader's MQTT
 - improvements to error handling in monitor job.
 - replaced `turn_off_leds_temporarily` with the more useful and more general `change_leds_intensities_temporarily`
 - UX improvements to the `pump_calibration` action
 - improving \*-Controller jobs:
    - `automation` is now a dict attribute (json in MQTT)
    - `automation_name` is a new published_setting, with string. This is what is read from the UI.
    - CLI has a slightly changed API to pick the automation
  - `pio_jobs_running` renamed to `pio_processes_running`

### 21.11.1
 - a version cut to test building images

### 21.11.0
 - too much to list

### 21.5.1

 - New plugin architecture
 - New database tables: `od_reading_statistics`, `stirring_rates`
 - New `pio` commands: `install-plugin`, `uninstall-plugins`
 - improvements to `continous_cycle` dosing automation.
 - hardware based PWM available on pins 1 & 3.

### 21.5.0

 - IR LED now turns off between OD readings. This allows other LEDs to trigger and take readings.
 - Removed leader jobs `time_series_aggregating` and `log_aggregating`
 - `logs` table in database has more metadata
 - New Kalman filter algorithm that includes an acceleration term
 - New database table, `kalman_filter_outputs`, stores the output of the internal Kalman Filter.
 - workers report back to leader additional system information including available memory and CPU usage.
 - Added new temperature control and temperature automations for this app and to the UI.
 - Added undervoltage alerts to logging
 - Added initial version of a plugin system
 - `pio run-always` for jobs not tied to an experiment (monitor, watchdog, etc.)
 - faster database backup sync between Pioreactors
 - Ability to measure your blank vials is available using the `pio run od_blank`, and in the UI under "Calibrate"
 - Smarter algorithm for displaying time series in the UI
 - Log table only shows the past 24 hours of events.


### 21.3.18

 - new dosing automation: `continous_cycle`. Designed for using the Pioreactor as an inline sensor.
 - stirring can now be dynamically adjusted between OD readings, for improved mixing (and hence more oxygen transfer). See settings in UI.
 - custom timezone support is added in config.ini
 - `download_experiment_data` is now called `export_experiment_data` - this has been updated on the UI as well.
 - unpausing stirring will return the rate to the previous value, not necessarily the default value.

### 21.3.3
 - fix GPIO mappings
 - fix keyboard interrupts in pump actions
 - fix race conditions in MQTT disconnects
 - fixed a bug where a job's state would change to `lost` when another job (of the same type) would try to start.
 - in `ADCReader`, changed from windowed moving average to exp. moving average to be more sensitive to recent changes in signal.
 - Growth rate calculating is a bit more robust to i) users pausing the job to inspect the vial, and ii) to changing the stirring speed.
 - mDNS alias is now configurable via the config.ini, so users could have multiple clusters without domain aliases colliding in the DNS.
 - fixed GPIO mappings for PWM Amplifiers
 - `inventory` in config.ini is now called `cluster.inventory`
 - `ui.overview.rename` in config.ini is now called `ui.rename`

### 21.2.4
 - fixed reconnect issues when leader went offline and then online
 - pausing `dosing_control` now pauses sub jobs `dosing_automation`
 - renamed `_algorithm` to `_automation` everywhere.
 - ADC measurements are now run at exact time intervals (previously there was some drift). The `adc` job now publishes metadata about it's recording times.
 - Improved error handling in `od_reading`


### 21.2.3

 - The `logs` table in the database now contains, by default, all the DEBUG and up logs
 from all Pioreactors. It also has a new column to denote the software source of the log. A separate topic is now set up for the logging in the UI.
 - `pioreactor.local` is now the default URL of the PioreactorUI.
 - on Pioreactor install, a seed experiment is created so users aren't dropped into a "blank" UI.
 - `pubsub.subscribe_and_callback` can now filter retained messages.
 - "algorithms" is now called "automations" throughout
 - reduced the number of threads per job
 - new topic for raw ADC measurements: `pioreactor/<unit>/<experiment>/adc/<channel>`
 - improved MQTT QOS for important jobs


### 21.2.2

 - `pios sync` is now `pios upgrade`.
 - `pio upgrade` requires flags: `--app` and / or `--ui` to upgrade the PioreactorApp and PioreactorUI respectively.


### 21.2.1

 - new SQL tables: `led_events`, `led_algorithm_settings`
 - `dosing_algorithm_settings` has a new schema: a json blob to represent any editable settings.
 - new `pio` command: `pio run led_intensity`, ex: `pio run led_intensity --channel B intensity 50`
 - new `pio` command: `pio update` will update the software to the latest code on Github (later will be latest released version), and if possible, update the UI code as well.
 - new library dependency `DAC43608` that supports our LED driver.
 - config.ini now has abstracted any RaspberryPi pins: we only refer to the PCB labels now in config.ini
 - `pio kill` can accept multiple jobs, ex: `pio kill stirring od_reading`
