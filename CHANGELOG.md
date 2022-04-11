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
 - `inventory` in config.ini is now called `network.inventory`
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
