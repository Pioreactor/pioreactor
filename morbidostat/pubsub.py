# -*- coding: utf-8 -*-
# pubsub
import socket
import threading
import time
import traceback
from click import echo, style
from paho.mqtt import publish as mqtt_publish
from paho.mqtt import subscribe as mqtt_subscribe
from morbidostat.config import leader_hostname


class QOS:
    AT_MOST_ONCE = 0
    AT_LEAST_ONCE = 1
    EXACTLY_ONCE = 2


def publish(topic, message, hostname=leader_hostname, verbose=0, retries=10, **mqtt_kwargs):
    retry_count = 1
    while True:
        try:
            mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)

            if (verbose == 1 and topic.endswith("log")) or verbose > 1:
                current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                echo(
                    style(f"{current_time} ", bold=True) + style(f"{topic}: ", fg="bright_blue") + style(f"{message}", fg="green")
                )
            return

        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout) as e:
            # possible that leader is down/restarting, keep trying, but log to local machine.
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            echo(
                style(f"{current_time}:", fg="white")
                + style(f"Attempt {retry_count}: Unable to connect to host: {hostname}. {str(e)}", fg="red")
            )
            time.sleep(5 * retry_count)  # linear backoff
            retry_count += 1

        if retry_count == retries:
            raise ConnectionRefusedError(f"{current_time}: Unable to connect to host: {hostname}. Exiting.")


def subscribe(topics, hostname=leader_hostname, retries=10, **mqtt_kwargs):
    retry_count = 1
    while True:
        try:
            return mqtt_subscribe.simple(topics, hostname=hostname, **mqtt_kwargs)

        except (ConnectionRefusedError, socket.gaierror, OSError, socket.timeout) as e:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            # possible that leader is down/restarting, keep trying, but log to local machine.
            echo(
                style(f"{current_time}:", fg="white")
                + style(f"Attempt {retry_count}: Unable to connect to host: {hostname}. {str(e)}", fg="red")
            )
            time.sleep(5 * retry_count)  # linear backoff
            retry_count += 1

        if retry_count == retries:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            raise ConnectionRefusedError(f"{current_time}: Unable to connect to host: {hostname}. Exiting.")


def subscribe_and_callback(callback, topics, hostname=leader_hostname, timeout=None, max_msgs=None, **mqtt_kwargs):
    """
    Creates a new thread, wrapping around paho's subscribe.callback. Callbacks only accept a single parameter, message.

    timeout: the client will only listen for <timeout> seconds before disconnecting.
    max_msgs: the client will process <max_msgs> messages before disconnecting.


    TODO: what happens when I lose connection to host?
    """

    def wrap_callback(actual_callback):
        def _callback(client, userdata, message):
            try:
                if "timeout" in userdata and time.time() - userdata["started_at"] > userdata["timeout"]:
                    client.disconnect()
                    return

                if "max_msgs" in userdata:
                    if userdata["count"] > userdata["max_msgs"]:
                        client.disconnect()
                        return
                    else:
                        userdata["count"] += 1

                return actual_callback(message)

            except Exception as e:
                traceback.print_exc()

                from morbidostat.whoami import unit, experiment

                publish(f"morbidostat/{unit}/{experiment}/error_log", str(e), verbose=1)

                raise e

        return _callback

    userdata = {}
    if timeout:
        userdata["started_at"] = time.time()
        userdata["timeout"] = timeout

    if max_msgs:
        userdata["count"] = 0
        userdata["max_msgs"] = max_msgs

    thread = threading.Thread(
        target=mqtt_subscribe.callback,
        args=(wrap_callback(callback), topics),
        kwargs={"hostname": hostname, "userdata": userdata, **mqtt_kwargs},
        daemon=True,
    )
    thread.start()
