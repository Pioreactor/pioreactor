### Upcoming

#### Bug fixes

 - Fix "End experiment" killing all jobs.
 - Fix `pio view-cache` not working outside the home directory.
 - Fixes for hardware HAT version 1.1.


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
