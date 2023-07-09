# -*- coding: utf-8 -*-
from __future__ import annotations

import random
import socket
import string
import threading
from enum import IntEnum
from time import sleep
from typing import Any
from typing import Callable
from typing import Optional

from paho.mqtt.client import Client as PahoClient

from pioreactor.config import leader_address
from pioreactor.types import MQTTMessage


class MQTT_TOPIC:
    def __init__(self, init: str):
        self.body = init

    def __truediv__(self, other: str | MQTT_TOPIC) -> MQTT_TOPIC:
        return MQTT_TOPIC(self.body + "/" + str(other))

    def __str__(self) -> str:
        return self.body

    def __repr__(self) -> str:
        return str(self)

    def __iter__(self):
        return iter(str(self))


PIOREACTOR = MQTT_TOPIC("pioreactor")


def add_hash_suffix(s: str) -> str:
    """Adds random 4-character hash to the end of a string.

    Args:
        s: The string to which the hash should be added.

    Returns:
        The string with the hash appended to it.
    """
    alphabet: str = string.ascii_lowercase + string.digits
    return s + "-" + "".join(random.choices(alphabet, k=4))


class Client(PahoClient):
    def __enter__(self) -> Client:
        return self

    def __exit__(self, *args):
        self.loop_stop()
        self.disconnect()

    def loop_stop(self):
        super().loop_stop()
        self._reset_sockets(sockpair_only=True)
        return self


class QOS(IntEnum):
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


def create_client(
    hostname: Optional[str] = None,
    last_will: Optional[dict] = None,
    client_id: str = "",
    keepalive=60,
    max_connection_attempts=3,
    clean_session=None,
    on_connect: Optional[Callable] = None,
    on_disconnect: Optional[Callable] = None,
    on_message: Optional[Callable] = None,
    userdata: Optional[dict] = None,
):
    """
    Create a MQTT client and connect to a host.
    """

    def default_on_connect(client: Client, userdata, flags, rc: int, properties=None):
        if rc > 1:
            from pioreactor.logging import create_logger
            from paho.mqtt.client import connack_string

            logger = create_logger("pubsub.create_client", to_mqtt=False)
            logger.error(f"Connection failed with error code {rc=}: {connack_string(rc)}")

    client = Client(
        client_id=add_hash_suffix(client_id) if client_id else "",
        clean_session=clean_session,
        userdata=userdata,
    )
    client.username_pw_set("pioreactor", "raspberry")

    if on_connect:
        client.on_connect = on_connect  # type: ignore
    else:
        client.on_connect = default_on_connect  # type: ignore

    if on_message:
        client.on_message = on_message

    if on_disconnect:
        client.on_disconnect = on_disconnect

    if last_will is not None:
        client.will_set(**last_will)

    if hostname is None:
        hostname = leader_address

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
    from paho.mqtt import publish as mqtt_publish
    import socket

    for retry_count in range(retries):
        try:
            mqtt_publish.single(
                topic,
                payload=message,
                hostname=hostname,
                auth={"username": "pioreactor", "password": "raspberry"},
                **mqtt_kwargs,
            )
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
    hostname: str = leader_address,
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

    retry_count = 1
    for retry_count in range(retries):
        try:
            lock: Optional[threading.Lock]

            def on_connect(client: Client, userdata, flags, rc) -> None:
                client.subscribe(userdata["topics"])
                return

            def on_message(client: Client, userdata, message: MQTTMessage) -> None:
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
            client.username_pw_set("pioreactor", "raspberry")
            client.on_connect = on_connect  # type: ignore
            client.on_message = on_message  # type: ignore
            client.connect(hostname)

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
        # create a new client
        def on_connect(client: Client, userdata: dict, *args):
            client.subscribe(userdata["topics"])

        userdata = {
            "topics": [(topic, mqtt_kwargs.pop("qos", 0)) for topic in topics],
            "name": name,
        }

        client = create_client(
            last_will=last_will,
            on_connect=on_connect,
            on_message=wrap_callback(callback),
            userdata=userdata,
            **mqtt_kwargs,
        )

    else:
        # user provided a client
        for topic in topics:
            client.message_callback_add(topic, wrap_callback(callback))
            client.subscribe(topic)

    return client


def prune_retained_messages(topics_to_prune: str = "#", hostname=leader_address):
    topics = []

    def on_message(message):
        topics.append(message.topic)

    client = subscribe_and_callback(on_message, topics_to_prune, hostname=hostname, timeout=1)

    for topic in topics.copy():
        publish(topic, None, retain=True, hostname=hostname)

    client.disconnect()


class collect_all_logs_of_level:
    # This code allows us to collect all logs of a certain level from a unit and experiment
    # We can use this to check that the logs are actually being published as we expect
    # We can also use this to check that the log levels are being set as we expect

    def __init__(self, log_level: str, unit: str, experiment: str) -> None:
        # set the log level we are looking for
        self.log_level = log_level.upper()
        # set the unit and experiment we are looking for
        self.unit = unit
        self.experiment = experiment
        # create a bucket for the logs
        self.bucket: list[dict] = []
        # subscribe to the logs
        self.client: Client = subscribe_and_callback(
            self._collect_logs_into_bucket,
            str(PIOREACTOR / self.unit / self.experiment / "logs" / "app"),
        )

    def _collect_logs_into_bucket(self, message):
        from json import loads

        # load the message
        log = loads(message.payload)
        # if the log level matches, add it to the bucket
        if log["level"] == self.log_level:
            self.bucket.append(log)

    def __enter__(self) -> list[dict]:
        return self.bucket

    def __exit__(self, *args):
        # stop listening for messages
        self.client.loop_stop()
        # disconnect from the broker
        self.client.disconnect()


def publish_to_pioreactor_cloud(
    endpoint: str, data_dict: Optional[dict] = None, data_str: Optional[str] = None
) -> None:
    """
    Parameters
    ------------
    endpoint: the function to send to the data to
    json: (optional) data to send in the body.

    """
    from pioreactor.mureq import post
    from pioreactor.whoami import get_hashed_serial_number, is_testing_env
    from pioreactor.utils.timing import current_utc_timestamp
    from json import dumps

    assert (data_dict is not None) or (data_str is not None)

    if is_testing_env():
        return

    if data_dict is not None:
        data_dict["hashed_serial_number"] = get_hashed_serial_number()
        data_dict["timestamp"] = current_utc_timestamp()
        body = dumps(data_dict).encode("utf-8")
    elif data_str is not None:
        body = data_str.encode("utf-8")

    headers = {"Content-type": "application/json", "Accept": "text/plain"}
    try:
        post(
            f"https://cloud.pioreactor.com/{endpoint}",
            body=body,
            headers=headers,
        )
    except Exception:
        pass
