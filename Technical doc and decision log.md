### Technical doc and decision log

1. MQTT events from the pioreactor units have the topic prefix `pioreactor/{unit number}/{experiment name}/`. We chose this because with this granularity, we can use the MQTT broker as a cache for values within an experiment. For example, after a unit goes offline, it can reconnect to the broker and have some "state" back. We can use the QOS and retain flags to manage this. This is useful for things like realtime growth rates & alt-media fraction.

2. The LED shines at near maximum brightness, and we tweak the feedback resistors to modulate the resulting voltage. Maximum LED brightness also also for the most light to get through the cultures, which will help push back saturation.

3. Since a unit can have multiple photodiodes at the same angle, it is simplest to have topics of the form `.../<angle>/<label>` where label enumerates through `A,B,C...`.

5. We attempt to follow the Homie device life cycle convention for background jobs. A job starts in `init` -> `ready` and then can be paused with `sleeping`. Jobs should safe exit by calling `disconnect`. The last-will message will set state to "lost".

5. Pausing a background job should be done using `pioreactor/<unit>/<experiment>/<job_name>/$state/set` with a message `"sleeping"`. This follows the Homie convention.

6. Changing, or setting an attribute, in a background job is done using `pioreactor/<unit>/<experiment>/<job_name>/<attr>/set`, inspired by the Homie convention, and the new value as the message. Jobs can implement _how_ to update (do I unpack a json? is it a float? etc.).

7. Attributes from background jobs are published (and retained) under `pioreactor/<unit>/<experiment>/<job_name>/<attr>`, following the Homie convention. This way, downstream consumers can listen for changes on these topics and update if needed (ex: the webui can show status of `volume`, `duty_cycle` etc.). Discovery of attributes is under `pioreactor/<unit>/<experiment>/<job_name>/$properties` (following Homie.)

7. Because of differences between the sensitivity of the sensors, the output of the LEDs, and other uncontrollable factors, we normalize the OD reading by the median of the first N values observed before going into the growth rate calculator. This means the _implied_ OD reading will start at or near 1, and scale from there. This makes choosing a single target OD across multiple units easier.

8. The leader runs all the units with the `pios` command, and individual workers (and leader) run with the `pio` command. The two follow the same convention, i.e. a command that works on `pio` should work on `pios`.

9. SQLite works well for a database for the storage of IoT data. I never will have more than one user, it can store and read json data, and has good documentation.

10. The io_controlling job will not execute if the latest readings are over 5 minutes old.

11. The photodiode is in photovoltaic mode because it is less noisy (trade off is that it is slower, but that's okay.)

12. All units can be addressed with the unit "number" `$broadcast` (Homie convention). For example, to change the target OD of all units, one can message `pioreactor/$broadcast/experiment/io_controlling/target_od/set`.

13. The pioreactor should always be able to run on RpiZeroWs - these are significantly cheaper. We don't ever need the peripherals on a regular RPi. However, RPiZeros are slower to execute, and can't sample OD as fast (about once per 5sec).

14. Parent jobs and subjobs: A parent job has the responsibility of disconnecting a subjob (which may have subjobs of its own). Eventually, I would like subjobs to know about their parents. Until then, there is an asymmetry.

15. <del>Killing threads: yes, I do, but I think I am forced to so long as I keep using the helper functions in paho. Killing a thread is a bad anti-pattern because it may be holding a critical resource (not so in my case: mqtt is designed to be closed abruptly), or it may have spawned its own threads. The latter is possible, and I should look carefully if this happens.</del> I no longer delete threads, but found a better solution by working with paho clients.

16. We can choose whether to clear attr from MQTT when we disconnect. From Homie: "Devices can remove old properties and nodes by publishing a zero-length payload on the respective topics."

17. `config.ini` files: the leader unit will ship a global config.ini to each unit during `pios sync`, but there exists a (possibly empty) local config.ini that overrides these settings. This is useful for changing PID or evolution parameters over units. Local config.ini are stores in `~/.pioreactor/config.ini`, and global config.ini are stored in `/etc/pioreactor/config.ini`. On `pios sync`, the leader copy its own global config.ini to the units global config.ini (`make install` needs to place it in the leader). The configs should be editable in the UI.

18. Changing name to `pioreactor`, including in the MQTT prefix. This better describes the project. Previously `mba` is now `pios` and `mb` is now `pio`.
