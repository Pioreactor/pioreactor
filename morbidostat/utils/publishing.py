# publishing

from paho.mqtt import publish as mqtt_publish
from morbidostat.utils import leader_hostname


def publish(topic, message, hostname=leader_hostname, verbose=False, **mqtt_kwargs):

    mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)
    if verbose:
        print(f"{topic}: {message}")

    return
