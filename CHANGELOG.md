### Upcoming

#### Enhancements
 - UI chart legend's will support more than 8 Pioreactors.
 - UI chart colors are consistent across charts in the Overview.
 - reduce the severity of some messages, so there will be less pop-ups in the UI.
 - UI performance improvements.
   - Upgraded to React 18
   - Removed unused dependencies
 - UI's code sections use syntax-highlighting and other nicer features for editing yaml and ini files.
 - App performance improvements
   - Upgrade paho-mqtt to 2.0
   - faster `pio kill`
   - faster job start from UI
 - more humane error messages.
 - updated temperature inference model.
 - added exponentiation `**` to profile expressions. Ex: `${{ pio1:growth_rate_calculating:growth_rate.growth_rate ** 0.5 }}`
 - added `random()` to profile expressions. This returns a number between 0 and 1. Ex: `${{ 25 + 25 * random() }} `


#### Bug fixes
 - fix `pio plugins` not working on workers.
 - fix `enable_dodging_od=0` for background jobs that can dodge OD.
 - fix jobs not cleaning up correctly if too many jobs try to end at the same time.
 - fix `pio kill` not returning the correct count of jobs being killed.
 - fix older Pioreactor HATs, with the ADS1115 chip, not have the method `from_voltage_to_raw_precise`.


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
