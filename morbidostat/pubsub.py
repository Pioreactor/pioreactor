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


def subscribe_and_callback(callback, topics, hostname=leader_hostname, **mqtt_kwargs):
    """
    Creates a new thread, wrapping around paho's subscribe.callback. Callbacks only accept a single parameter, message.

    TODO: what happens when I lose connection to host?
    """

    def job_callback(actual_callback):
        def _callback(_, __, message):
            try:
                return actual_callback(message)
            except Exception as e:
                # TODO: this doesn't always fire...
                traceback.print_exc()

                from morbidostat.whoami import unit, experiment

                publish(f"morbidostat/{unit}/{experiment}/error_log", str(e), verbose=1)

        return _callback

    thread = threading.Thread(
        target=mqtt_subscribe.callback,
        kwargs={"callback": job_callback(callback), "topics": topics, "hostname": hostname},
        daemon=True,
    )
    thread.start()
