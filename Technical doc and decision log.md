### Technical doc and decision log

1. MQTT events from the morbidostat units have the topic prefix `morbidostat/{unit number}/{experiment name}/`. We choose this because with this granularity, we can use the MQTT broker as a cache for values within an experiment. For example, after a unit goes offline, it can reconnect to the broker and have some "state" back. We can use the QOS and retain flags to manage this. This is useful for things like realtime growth rates & alt-media fraction.
