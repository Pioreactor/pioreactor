### Next

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
