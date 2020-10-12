### Technical doc and decision log

1. MQTT events from the morbidostat units have the topic prefix `morbidostat/{unit number}/{experiment name}/`. We chose this because with this granularity, we can use the MQTT broker as a cache for values within an experiment. For example, after a unit goes offline, it can reconnect to the broker and have some "state" back. We can use the QOS and retain flags to manage this. This is useful for things like realtime growth rates & alt-media fraction.

2. The LED shines at near maximum brightness, and we tweak the feedback resistors to modulate the resulting voltage.

3. Since a unit can have multiple photodiodes at the same angle, it is simplest to have topics of the form `.../<angle>/<label>` where label enumerates through `A,B,C...`.

4. For now, Node-Red is doing all the MQTT reading and time series aggregation and saving the data to the filesystem. This is simplest for now: the frontend reads these files, and later I can replace Node-Red with a proper backend.
