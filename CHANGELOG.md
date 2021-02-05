
### 21.2.3

 - The `logs` table in the database now contains, by default, all the DEBUG and up logs
 from all Pioreactors. It also has a new column to denote the software source of the log. A separate topic is now set up for the logging in the UI.
 - `pioreactor.local` is now the default URL of the PioreactorUI.
 - on Pioreactor install, a seed experiment is created so users aren't dropped into a "blank" UI.
 - `pubsub.subscribe_and_callback` can now filter retained messages.


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
