# publishing

from paho.mqtt import publish as mqtt_publish
from morbidostat.utils import config

def publish(topic, message, hostname=config['network']['leader_hostname'], verbose=False):

    mqtt_publish.single(topic, payload=message, hostname=hostname)
    if verbose:
        print(message)

    return