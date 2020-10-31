### Technical doc and decision log

1. MQTT events from the morbidostat units have the topic prefix `morbidostat/{unit number}/{experiment name}/`. We chose this because with this granularity, we can use the MQTT broker as a cache for values within an experiment. For example, after a unit goes offline, it can reconnect to the broker and have some "state" back. We can use the QOS and retain flags to manage this. This is useful for things like realtime growth rates & alt-media fraction.

2. The LED shines at near maximum brightness, and we tweak the feedback resistors to modulate the resulting voltage.

3. Since a unit can have multiple photodiodes at the same angle, it is simplest to have topics of the form `.../<angle>/<label>` where label enumerates through `A,B,C...`.

4. For now, Node-Red is doing all the MQTT reading and time series aggregation and saving the aggregated data to the filesystem. This is simplest for now: the frontend reads these files, and later I can replace Node-Red with a proper backend.

5. Pausing a background job should be done using `morbidostat/<unit>/<experiment>/<job_name>/active/set` with a binary message (1 is active, 0 is inactive)

6. Changing, or setting an attribute, in a background job is done using `morbidostat/<unit>/<experiment>/<job_name>/<attr>/set`, inspired by the Homie convention, and the new value as the message. Jobs can implement _how_ to update (do I unpack a json? is it a float? etc.). The utility `utils.split_topic_for_setting` is useful here.

7. Attributes from background jobs are published (and retained) under `morbidostat/<unit>/<experiment>/<job_name>/<attr>`, following the Homie convention. This way, downstream consumers can listen for changes on these topics and update if needed (ex: the webui can show status of `active`, `stir_rate` etc.)

7. Because of differences between the sensitivity of the sensors, the output of the LEDs, and other uncontrollable factors, we normalize the implied OD reading by the median of the first 20 values observed. This means the implied OD reading will start at or near 1, and scale from there. This makes choosing a single target OD across multiple units easier.

8. The leader runs all the units with the `mba` command, and individual workers run with the `mb` command.

9. SQLite works well for a database for the storage of IoT data. I never will have more than one user, it can store and read json data, and has good documentation.

10. The io_controlling will not execute if the latest readings are over 5 minutes old.

11. The photodiode is in photovoltaic mode because it is less noisy (trade off is that it is slower, but that's okay.)
