# -*- coding: utf-8 -*-
import random
import socket
import string
import threading
from contextlib import suppress
from time import sleep
from typing import Any
from typing import Callable

from msgspec import Struct
from msgspec.json import decode as loads
from paho.mqtt.client import Client as PahoClient
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.enums import MQTTErrorCode
from pioreactor import mureq
from pioreactor import types as pt
from pioreactor.config import config
from pioreactor.config import leader_address
from pioreactor.config import mqtt_address


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
    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: object) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        self.loop_stop()
        self.disconnect()
        self._reset_sockets(sockpair_only=True)  # reduce the FD explosion.

    def loop_stop(self) -> MQTTErrorCode:
        # fast exits
        thread = self._thread
        if thread is None:
            return MQTTErrorCode.MQTT_ERR_INVAL
        self._thread_terminate = True
        # Wake the network loop (select) so it can observe _thread_terminate promptly.
        # Avoid closing sockpair fds while the loop thread might be blocked on recv.
        if self._sockpairW is not None:
            try:
                self._sockpairW.send(b"x")
            except OSError:
                pass

        if threading.current_thread() != thread:
            thread.join()
        return MQTTErrorCode.MQTT_ERR_SUCCESS


class QOS:
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


def create_client(
    hostname: str = mqtt_address,
    last_will: dict[str, Any] | None = None,
    client_id: str = "",
    keepalive: int = 60,
    max_connection_attempts: int = 3,
    clean_session: bool | None = None,
    on_connect: Callable[..., Any] | None = None,
    on_disconnect: Callable[..., Any] | None = None,
    on_subscribe: Callable[..., Any] | None = None,
    on_message: Callable[..., Any] | None = None,
    userdata: dict[str, Any] | None = None,
    port: int = config.getint("mqtt", "broker_port", fallback=1883),
    tls: bool = config.getboolean("mqtt", "use_tls", fallback="0"),
    skip_loop: bool = False,
) -> Client:
    """
    Create a MQTT client and connect to a host.
    """

    def default_on_connect(
        client: Client, userdata: Any, flags: Any, rc: int, properties: Any = None
    ) -> None:
        if rc > 1:
            from pioreactor.logging import create_logger
            from paho.mqtt.client import connack_string

            logger = create_logger("pubsub.create_client", to_mqtt=False)
            logger.error(f"Connection failed with error code {rc=}: {connack_string(rc)}")

    client = Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        # Note: if empty string, paho or mosquitto will autogenerate a good client id.
        client_id=add_hash_suffix(client_id) if client_id else "",
        clean_session=clean_session,
        userdata=userdata,
    )
    client.username_pw_set(
        config.get("mqtt", "username", fallback="pioreactor"),
        config.get("mqtt", "password", fallback="raspberry"),
    )
    # set a finite queue for QOS>0 messages, so that if we lose connection, we don't store an unlimited number of messages. When the network comes back on, we don't want
    # a storm of messages (it also causes problems when multiple triggers are sent to execute methods.)
    client.max_queued_messages_set(100)

    if tls:
        import ssl

        client.tls_set(tls_version=ssl.PROTOCOL_TLS)

    if on_connect:
        client.on_connect = on_connect
    else:
        client.on_connect = default_on_connect  # type: ignore

    if on_message:
        client.on_message = on_message

    if on_disconnect:
        client.on_disconnect = on_disconnect

    if on_subscribe:
        client.on_subscribe = on_subscribe

    if last_will is not None:
        client.will_set(**last_will)

    for retries in range(1, max_connection_attempts + 1):
        try:
            client.connect(hostname, port, keepalive=keepalive)
        except (socket.gaierror, OSError):
            if retries == max_connection_attempts:
                break
            sleep(2 * retries)
        else:
            if not skip_loop:
                client.loop_start()
            break
    return client


def publish(
    topic: str, message: str | bytes | bytearray | int | float | None, retries: int = 3, **mqtt_kwargs: Any
) -> None:
    for retry_count in range(retries):
        try:
            with create_client() as client:
                msg = client.publish(
                    topic,
                    message,
                    **mqtt_kwargs,
                )
                msg.wait_for_publish(timeout=10)

                if not msg.is_published():
                    raise RuntimeError()

            return
        except RuntimeError:
            # possible that leader is down/restarting, keep trying, but log to local machine.
            from pioreactor.logging import create_logger

            logger = create_logger("pubsub.publish", to_mqtt=False)
            logger.debug(
                f"Attempt {retry_count}: Unable to connect to MQTT",
                exc_info=True,
            )
            sleep(3 * retry_count)  # linear backoff

    else:
        logger = create_logger("pubsub.publish", to_mqtt=False)
        logger.error("Unable to connect to MQTT.")
        raise ConnectionRefusedError("Unable to connect to MQTT.")


def subscribe(
    topics: str | list[str],
    timeout: float | None = None,
    allow_retained: bool = True,
    name: str | None = None,
    **mqtt_kwargs: Any,
) -> pt.MQTTMessage | None:
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

    lock: threading.Lock | None

    def on_connect(
        client: Client, userdata: dict[str, Any], flags: Any, reason_code: Any, properties: Any
    ) -> None:
        client.subscribe(userdata["topics"])
        return

    def on_message(client: Client, userdata: dict[str, Any], message: pt.MQTTMessage) -> None:
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
        "topics": [(topic, mqtt_kwargs.pop("qos", QOS.EXACTLY_ONCE)) for topic in topics],
        "messages": None,
        "lock": lock,
    }
    client = create_client(on_connect=on_connect, on_message=on_message, userdata=userdata, skip_loop=True)

    if timeout is None:
        client.loop_forever()
    else:
        assert lock is not None
        lock.acquire()
        client.loop_start()
        lock.acquire(timeout=timeout)
        client.shutdown()

    return userdata["messages"]


def subscribe_and_callback(
    callback: Callable[[pt.MQTTMessage], Any],
    topics: str | list[str],
    last_will: dict[str, Any] | None = None,
    name: str | None = None,
    allow_retained: bool = True,
    client: Client | None = None,
    on_cleanup: list[Callable[[], None]] | None = None,
    **mqtt_kwargs: Any,
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
    assert callable(callback), "callback should be callable - do you need to change the order of arguments?"

    def remove_callback_subscription(client: Client, topic: str) -> None:
        # This cleanup assumes effective ownership of this topic filter on the provided client.
        # Paho stores one callback per topic filter, and unsubscribe() removes the filter for the
        # whole client. On a genuinely shared long-lived client, this can clobber another caller's
        # callback/subscription if they reused the same topic. Today we accept that exclusivity risk
        # to avoid unbounded listener growth, but it is a known failure mode of this teardown path.
        with suppress(KeyError, ValueError):
            client.message_callback_remove(topic)

        with suppress(ValueError):
            client.unsubscribe(topic)

    def wrap_callback(actual_callback: Callable[[pt.MQTTMessage], Any]) -> Callable[..., Any]:
        def _callback(client: Client, userdata: dict[str, Any], message: pt.MQTTMessage) -> Any:
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
        def on_connect(client: Client, userdata: dict[str, Any], *args: Any) -> None:
            client.subscribe(userdata["topics"])

        def on_subscribe(
            client: Client,
            userdata: dict[str, Any],
            mid: int,
            granted_qos: tuple[int, ...],
            properties: Any = None,
        ) -> None:
            sub_ready.set()

        sub_ready = threading.Event()

        userdata = {
            "topics": [(topic, mqtt_kwargs.pop("qos", QOS.EXACTLY_ONCE)) for topic in topics],
            "name": name,
        }

        client = create_client(
            last_will=last_will,
            on_connect=on_connect,
            on_message=wrap_callback(callback),
            on_subscribe=on_subscribe,
            userdata=userdata,
            **mqtt_kwargs,
        )

        if not sub_ready.wait(timeout=5):
            raise RuntimeError("MQTT subscribe timeout")
    else:
        # user provided a client
        for topic in topics:
            wrapped_callback = wrap_callback(callback)
            client.message_callback_add(topic, wrapped_callback)
            client.subscribe(topic)

            if on_cleanup is not None:

                def cleanup_subscription(topic: str = topic) -> None:
                    remove_callback_subscription(client, topic)

                on_cleanup.append(cleanup_subscription)

    return client


def prune_retained_messages(topics_to_prune: str = "#") -> None:
    topics = []

    def on_message(message: pt.MQTTMessage) -> None:
        topics.append(message.topic)

    client = subscribe_and_callback(on_message, topics_to_prune, allow_retained=True)
    sleep(0.05)  # to collect
    for topic in topics.copy():
        client.publish(topic, None, retain=True)

    client.shutdown()


class collect_all_logs_of_level:
    # This code allows us to collect all logs of a certain level from a unit and experiment
    # We can use this to check that the logs are actually being published as we expect
    # We can also use this to check that the log levels are being set as we expect

    def __init__(self, log_level: str, unit: pt.Unit, experiment: pt.Experiment) -> None:
        # set the log level we are looking for
        self.log_level = log_level.upper()
        # set the unit and experiment we are looking for
        self.unit = unit
        self.experiment = experiment
        # create a bucket for the logs
        self.bucket: list[dict[str, Any]] = []
        # subscribe to the logs

        self.client: Client = subscribe_and_callback(
            self._collect_logs_into_bucket,
            f"pioreactor/{self.unit}/{self.experiment}/logs/+/{self.log_level.lower()}",
            allow_retained=False,
            client_id=f"{self.unit}_{self.experiment}_{self.log_level}_log_collector",
        )

    def _collect_logs_into_bucket(self, message: pt.MQTTMessage) -> None:
        # load the message
        log = loads(message.payload)
        # if the log level matches, add it to the bucket
        if log["level"] == self.log_level:
            self.bucket.append(log)

    def __enter__(self) -> list[dict[str, Any]]:
        return self.bucket

    def __exit__(self, *args: object) -> None:
        self.client.shutdown()


def conform_and_validate_api_endpoint(endpoint: str) -> str:
    endpoint = endpoint.removeprefix("/")
    if not (endpoint.startswith("api/") or endpoint.startswith("unit_api/")):
        raise ValueError(f"/{endpoint} is not a valid Pioreactor API.")

    return endpoint


def create_webserver_path(address: str, endpoint: str) -> str:
    # pioreactor cluster specific (note the use of protocol and ports from our config!)
    # Most commonly, address can be an mdns name (test.local), or an IP address.
    port = config.getint("ui", "port", fallback=80)
    proto = config.get("ui", "proto", fallback="http")
    endpoint = conform_and_validate_api_endpoint(endpoint)
    return f"{proto}://{address}:{port}/{endpoint}"


def get_from(address: str, endpoint: str, **kwargs: Any) -> mureq.Response:
    # pioreactor cluster specific
    return mureq.get(create_webserver_path(address, endpoint), **kwargs)


def get_from_leader(endpoint: str, timeout: int = 5, **kwargs: Any) -> mureq.Response:
    return get_from(leader_address, endpoint, timeout=timeout, **kwargs)


def put_into(
    address: str,
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    **kwargs: Any,
) -> mureq.Response:
    # pioreactor cluster specific
    return mureq.put(create_webserver_path(address, endpoint), body=body, json=json, **kwargs)


def put_into_leader(
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    timeout: int = 5,
    **kwargs: Any,
) -> mureq.Response:
    return put_into(leader_address, endpoint, body=body, json=json, timeout=timeout, **kwargs)


def patch_into(
    address: str,
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    **kwargs: Any,
) -> mureq.Response:
    # pioreactor cluster specific
    return mureq.patch(create_webserver_path(address, endpoint), body=body, json=json, **kwargs)


def patch_into_leader(
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    timeout: int = 5,
    **kwargs: Any,
) -> mureq.Response:
    return patch_into(leader_address, endpoint, body=body, json=json, timeout=timeout, **kwargs)


def post_into(
    address: str,
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    **kwargs: Any,
) -> mureq.Response:
    # pioreactor cluster specific
    return mureq.post(create_webserver_path(address, endpoint), body=body, json=json, **kwargs)


def post_into_leader(
    endpoint: str,
    body: bytes | None = None,
    json: dict[str, Any] | Struct | None = None,
    timeout: int = 5,
    **kwargs: Any,
) -> mureq.Response:
    return post_into(leader_address, endpoint, body=body, json=json, timeout=timeout, **kwargs)


def delete_from(address: str, endpoint: str, **kwargs: Any) -> mureq.Response:
    # pioreactor cluster specific
    return mureq.delete(create_webserver_path(address, endpoint), **kwargs)


def delete_from_leader(endpoint: str, timeout: int = 5, **kwargs: Any) -> mureq.Response:
    return delete_from(leader_address, endpoint, timeout=timeout, **kwargs)
