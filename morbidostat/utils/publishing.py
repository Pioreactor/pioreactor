# publishing
from paho.mqtt import publish as mqtt_publish
from morbidostat.utils import leader_hostname
import time


def publish(topic, message, hostname=leader_hostname, verbose=False, **mqtt_kwargs):

    try:
        mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)
        if verbose:
            print(f"{topic}: {message}")
    except ConnectionRefusedError:
        # possible that leader is down/restarting
        time.sleep(5)
        mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)

    return
