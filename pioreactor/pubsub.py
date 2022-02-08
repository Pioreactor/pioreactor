# -*- coding: utf-8 -*-
from __future__ import annotations

import socket
import threading
import time
from enum import IntEnum
from typing import Any
from typing import Callable
from typing import Optional

from paho.mqtt import publish as mqtt_publish  # type: ignore
from paho.mqtt.client import Client  # type: ignore
from paho.mqtt.client import connack_string  # type: ignore

from pioreactor.config import leader_hostname
from pioreactor.types import MQTTMessage


class QOS(IntEnum):
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


def create_client(
    hostname: str = leader_hostname,
    last_will: Optional[dict] = None,
    client_id: Optional[str] = None,
    keepalive=60,
    max_retries=3,
) -> Client:
    """
    Create a MQTT client and connect to a host.
    """

    def on_connect(client: Client, userdata, flags, rc: int, properties=None):
        if rc > 1:
            from pioreactor.logging import create_logger

            logger = create_logger("pubsub.create_client", to_mqtt=False)
            logger.error(f"Connection failed with error code {rc=}: {connack_string(rc)}")

    client = Client(client_id=client_id)
    client.on_connect = on_connect

    if last_will is not None:
        client.will_set(**last_will)

    for retries in range(1, max_retries + 1):
        try:
            client.connect(hostname, keepalive=keepalive)
        except (socket.gaierror, OSError):
            if retries == max_retries:
                break
            time.sleep(retries * 2)
        else:
            client.loop_start()
            break

    return client


def publish(
    topic: str, message, hostname: str = leader_hostname, retries: int = 10, **mqtt_kwargs
):

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
            time.sleep(5 * retry_count)  # linear backoff

    else:

        logger = create_logger("pubsub.publish", to_mqtt=False)
        logger.error(f"Unable to connect to host: {hostname}.")
        raise ConnectionRefusedError(f"Unable to connect to host: {hostname}.")


def publish_multiple(
    list_of_topic_message_tuples, hostname=leader_hostname, retries=10, **mqtt_kwargs
):
    """
    list_of_topic_message_tuples is of the form ("<topic>", "<payload>", qos, retain)

    """
    for retry_count in range(retries):
        try:
            mqtt_publish.multiple(
                list_of_topic_message_tuples, hostname=hostname, **mqtt_kwargs
            )
            return
        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout):
            # possible that leader is down/restarting, keep trying, but log to local machine.
            from pioreactor.logging import create_logger

            logger = create_logger("pubsub.publish_multiple", to_mqtt=False)
            logger.debug(
                f"Attempt {retry_count}: Unable to connect to host: {hostname}",
                exc_info=True,
            )
            time.sleep(5 * retry_count)  # linear backoff

    else:

        logger = create_logger("pubsub.publish_multiple", to_mqtt=False)
        logger.error(f"Unable to connect to host: {hostname}. Exiting.")
        raise ConnectionRefusedError(f"Unable to connect to host: {hostname}.")


def subscribe(
    topics: str | list[str],
    hostname=leader_hostname,
    retries: int = 10,
    timeout: Optional[float] = None,
    allow_retained: bool = True,
    **mqtt_kwargs,
) -> Optional[MQTTMessage]:
    """
    Modeled closely after the paho version, this also includes some try/excepts and
    a timeout. Note that this _does_ disconnect after receiving a single message.

    A failure case occurs if this is called in a thread (eg: a callback) and is waiting
    indefinitely for a message. The parent job may not exit properly.

    """

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
            client.connect(leader_hostname)

            if timeout is None:
                client.loop_forever()
            else:
                assert lock is not None
                lock.acquire()
                client.loop_start()
                lock.acquire(timeout=timeout)
                client.loop_stop()
                client._reset_sockets(sockpair_only=True)
                client.disconnect()

            return userdata["messages"]

        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout):
            from pioreactor.logging import create_logger

            logger = create_logger("pubsub.subscribe", to_mqtt=False)
            logger.debug(
                f"Attempt {retry_count}: Unable to connect to host: {hostname}",
                exc_info=True,
            )

            time.sleep(5 * retry_count)  # linear backoff

    else:
        logger = create_logger("pubsub.subscribe", to_mqtt=False)
        logger.error(f"Unable to connect to host: {hostname}. Exiting.")
        raise ConnectionRefusedError(f"Unable to connect to host: {hostname}.")


def subscribe_and_callback(
    callback: Callable[[MQTTMessage], Any],
    topics: str | list[str],
    hostname: str = leader_hostname,
    last_will: Optional[dict] = None,
    job_name: Optional[str] = None,
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
    job_name:
        Optional: provide the job name, and logging will include it.
    allow_retained: bool
        if True, all messages are allowed, including messages that the broker has retained. Note
        that client can fire a msg with retain=True, but because the broker is serving it to a
        subscriber "fresh", it will have retain=False on the client side. More here:
        https://github.com/eclipse/paho.mqtt.python/blob/master/src/paho/mqtt/client.py#L364
    """
    assert callable(
        callback
    ), "callback should be callable - do you need to change the order of arguments?"

    def on_connect(client: Client, userdata: dict, *args):
        client.subscribe(userdata["topics"])

    def wrap_callback(actual_callback: Callable[[MQTTMessage], Any]) -> Callable:
        def _callback(client: Client, userdata: dict, message):
            try:

                if not allow_retained and message.retain:
                    return

                return actual_callback(message)

            except Exception as e:
                from pioreactor.logging import create_logger

                logger = create_logger(userdata.get("job_name", "pioreactor"))
                logger.error(e, exc_info=True)
                raise e

        return _callback

    topics = [topics] if isinstance(topics, str) else topics
    userdata = {
        "topics": [(topic, mqtt_kwargs.pop("qos", 0)) for topic in topics],
        "job_name": job_name,
    }

    if client is None:
        user_provided = False
        client = Client(userdata=userdata)
    else:
        # user provided a client
        user_provided = True
        client.user_data_set(userdata)

    client.on_connect = on_connect
    client.on_message = wrap_callback(callback)

    if last_will is not None:
        client.will_set(**last_will)

    if not user_provided:
        client.connect(leader_hostname, **mqtt_kwargs)
        client.loop_start()

    return client


def prune_retained_messages(topics_to_prune="#", hostname=leader_hostname):
    topics = []

    def on_message(message):
        topics.append(message.topic)

    client = subscribe_and_callback(
        on_message, topics_to_prune, hostname=hostname, timeout=1
    )

    for topic in topics.copy():
        publish(topic, None, retain=True, hostname=hostname)

    client.disconnect()


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
    from pioreactor.utils.timing import current_utc_time

    if is_testing_env():
        return

    if json is not None:
        json["rpi_uuid"] = get_uuid()
        json["timestamp"] = current_utc_time()

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
