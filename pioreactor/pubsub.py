# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
from enum import IntEnum
from time import sleep
from typing import Any
from typing import Callable
from typing import Optional

from paho.mqtt.client import Client as PahoClient  # type: ignore

from pioreactor.config import leader_address
from pioreactor.types import MQTTMessage


class QOS(IntEnum):
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


class Client(PahoClient):
    def loop_stop(self):
        super().loop_stop()
        self._reset_sockets(sockpair_only=True)
        return self


def create_client(
    hostname: str = leader_address,
    last_will: Optional[dict] = None,
    client_id: Optional[str] = None,
    keepalive=60,
    max_connection_attempts=3,
    clean_session=None,
) -> Client:
    """
    Create a MQTT client and connect to a host.
    """
    import socket

    def on_connect(client: Client, userdata, flags, rc: int, properties=None):
        if rc > 1:
            from pioreactor.logging import create_logger
            from paho.mqtt.client import connack_string  # type: ignore

            logger = create_logger("pubsub.create_client", to_mqtt=False)
            logger.error(f"Connection failed with error code {rc=}: {connack_string(rc)}")

    client = Client(client_id=client_id, clean_session=clean_session)
    client.on_connect = on_connect

    if last_will is not None:
        client.will_set(**last_will)

    for retries in range(1, max_connection_attempts + 1):
        try:
            client.connect(hostname, keepalive=keepalive)
        except (socket.gaierror, OSError):
            if retries == max_connection_attempts:
                break
            sleep(retries * 2)
        else:
            client.loop_start()
            break

    return client


def publish(
    topic: str, message, hostname: str = leader_address, retries: int = 10, **mqtt_kwargs
) -> None:
    from paho.mqtt import publish as mqtt_publish  # type: ignore
    import socket

    for retry_count in range(retries):
        try:
            mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)
            return
        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout):
            # possible that leader is down/restarting, keep trying, but log to local machine.
            from pioreactor.logging import create_logger

            logger = create_logger("pubsub.publish", to_mqtt=False)
            logger.debug(
                f"Attempt {retry_count}: Unable to connect to host: {hostname}",
                exc_info=True,
            )
            sleep(3 * retry_count)  # linear backoff

    else:

        logger = create_logger("pubsub.publish", to_mqtt=False)
        logger.error(f"Unable to connect to host: {hostname}.")
        raise ConnectionRefusedError(f"Unable to connect to host: {hostname}.")


def subscribe(
    topics: str | list[str],
    hostname=leader_address,
    retries: int = 5,
    timeout: Optional[float] = None,
    allow_retained: bool = True,
    name: Optional[str] = None,
    **mqtt_kwargs,
) -> Optional[MQTTMessage]:
    """
    Modeled closely after the paho version, this also includes some try/excepts and
    a timeout. Note that this _does_ disconnect after receiving a single message.

    A failure case occurs if this is called in a thread (eg: a callback) and is waiting
    indefinitely for a message. The parent job may not exit properly.

    Parameters
    ------------
    topics: str, list of str
    name:
        Optional: provide a name, and logging will include it.
    """
    import socket

    retry_count = 1
    for retry_count in range(retries):
        try:

            lock: Optional[threading.Lock]

            def on_connect(client, userdata, flags, rc):
                client.subscribe(userdata["topics"])
                return

            def on_message(client, userdata, message: MQTTMessage):
                if not allow_retained and message.retain:
                    return

                userdata["messages"] = message
                client.disconnect()

                if userdata["lock"]:
                    userdata["lock"].release()

                return

            if timeout:
                lock = threading.Lock()
            else:
                lock = None

            topics = [topics] if isinstance(topics, str) else topics
            userdata: dict[str, Any] = {
                "topics": [(topic, mqtt_kwargs.pop("qos", 0)) for topic in topics],
                "messages": None,
                "lock": lock,
            }

            client = Client(userdata=userdata)
            client.on_connect = on_connect
            client.on_message = on_message
            client.connect(leader_address)

            if timeout is None:
                client.loop_forever()
            else:
                assert lock is not None
                lock.acquire()
                client.loop_start()
                lock.acquire(timeout=timeout)
                client.loop_stop()
                client.disconnect()

            return userdata["messages"]

        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout):
            from pioreactor.logging import create_logger

            logger = create_logger(name or "pubsub.subscribe", to_mqtt=False)
            logger.debug(
                f"Attempt {retry_count}: Unable to connect to host: {hostname}",
                exc_info=True,
            )

            sleep(3 * retry_count)  # linear backoff

    else:
        logger = create_logger(name or "pubsub.subscribe", to_mqtt=False)
        logger.error(f"Unable to connect to host: {hostname}. Exiting.")
        raise ConnectionRefusedError(f"Unable to connect to host: {hostname}.")


def subscribe_and_callback(
    callback: Callable[[MQTTMessage], Any],
    topics: str | list[str],
    hostname: str = leader_address,
    last_will: Optional[dict] = None,
    name: Optional[str] = None,
    allow_retained: bool = True,
    client: Optional[Client] = None,
    **mqtt_kwargs,
) -> Client:
    """
    Creates a new thread, wrapping around paho's subscribe.callback. Callbacks only accept a single parameter, message.

    Parameters
    -------------
    last_will: dict
        a dictionary describing the last will details: topic, qos, retain, msg.
    name:
        Optional: provide a name, and logging will include it.
    allow_retained: bool
        if True, all messages are allowed, including messages that the broker has retained. Note
        that client can fire a msg with retain=True, but because the broker is serving it to a
        subscriber "fresh", it will have retain=False on the client side. More here:
        https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L364
    """
    assert callable(
        callback
    ), "callback should be callable - do you need to change the order of arguments?"

    def wrap_callback(actual_callback: Callable[[MQTTMessage], Any]) -> Callable:
        def _callback(client: Client, userdata: dict, message):
            try:

                if not allow_retained and message.retain:
                    return

                return actual_callback(message)

            except Exception as e:
                from pioreactor.logging import create_logger

                logger = create_logger(userdata.get("name", "pioreactor"))
                logger.error(e, exc_info=True)
                raise e

        return _callback

    topics = [topics] if isinstance(topics, str) else topics

    if client is None:

        def on_connect(client: Client, userdata: dict, *args):
            client.subscribe(userdata["topics"])

        userdata = {
            "topics": [(topic, mqtt_kwargs.pop("qos", 0)) for topic in topics],
            "name": name,
        }

        client = Client(userdata=userdata)

        client.on_connect = on_connect
        client.on_message = wrap_callback(callback)

        client.connect(leader_address, **mqtt_kwargs)
        client.loop_start()
    else:
        # user provided a client
        for topic in topics:
            client.message_callback_add(topic, wrap_callback(callback))
            client.subscribe(topic)

    if last_will is not None:
        client.will_set(**last_will)

    return client


def prune_retained_messages(topics_to_prune="#", hostname=leader_address):
    topics = []

    def on_message(message):
        topics.append(message.topic)

    client = subscribe_and_callback(on_message, topics_to_prune, hostname=hostname, timeout=1)

    for topic in topics.copy():
        publish(topic, None, retain=True, hostname=hostname)

    client.disconnect()


class collect_all_logs_of_level:
    def __init__(self, log_level, unit, experiment):
        self.unit = unit
        self.log_level = log_level.upper()
        self.experiment = experiment
        self.bucket = []
        self.client = subscribe_and_callback(
            self._collect_logs_into_bucket,
            f"pioreactor/{self.unit}/{self.experiment}/logs/app",
        )

    def _collect_logs_into_bucket(self, message):
        from json import loads

        log = loads(message.payload)
        if log["level"] == self.log_level:
            self.bucket.append(log)

    def __enter__(self):
        return self.bucket

    def __exit__(self, *args):
        self.client.loop_stop()
        self.client.disconnect()


def publish_to_pioreactor_cloud(endpoint: str, data=None, json=None):
    """
    Parameters
    ------------
    endpoint: the function to send to the data to
    data: (optional) Dictionary, list of tuples, bytes, or file-like object to send in the body.
    json: (optional) json data to send in the body.

    """
    from pioreactor.mureq import post
    from pioreactor.whoami import get_uuid, is_testing_env
    from pioreactor.utils.timing import current_utc_timestamp

    if is_testing_env():
        return

    if json is not None:
        json["rpi_uuid"] = get_uuid()
        json["timestamp"] = current_utc_timestamp()

    headers = {"Content-type": "application/json", "Accept": "text/plain"}
    try:
        post(
            f"https://cloud.pioreactor.com/{endpoint}",
            data=data,
            json=json,
            headers=headers,
        )
    except Exception:
        pass
