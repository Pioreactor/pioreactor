# -*- coding: utf-8 -*-
# pubsub
import socket
import threading
import time
from click import echo, style
from paho.mqtt import publish as mqtt_publish
from paho.mqtt import subscribe as mqtt_subscribe
from morbidostat.utils import leader_hostname


def publish(topic, message, hostname=leader_hostname, verbose=False, retries=10, **mqtt_kwargs):

    retry = 1
    while True:
        try:
            mqtt_publish.single(topic, payload=message, hostname=hostname, **mqtt_kwargs)

            if verbose:
                current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                echo(
                    style(f"{current_time} ", bold=True) + style(f"{topic}: ", fg="bright_blue") + style(f"{message}", fg="green")
                )
            return

        except (ConnectionRefusedError, socket.gaierror) as e:
            # possible that leader is down/restarting, keep trying, but log to local machine.
            publish(
                "error_log",
                f"Attempt {retry}: Unable to connect to host: {hostname}. {str(e)}",
                hostname="localhost",
                retain=True,
            )

            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            echo(
                style(f"{current_time}:", fg="white")
                + style(f"Attempt {retry}: Unable to connect to host: {hostname}. {str(e)}", fg="red")
            )
            time.sleep(5 * retry)  # linear backoff
            retry += 1

        if retry == retries:
            raise ConnectionRefusedError(f"{current_time}: Unable to connect to host: {hostname}. Exiting.")


def subscribe(topics, hostname=leader_hostname, retries=10, **mqtt_kwargs):
    retry = 1

    while True:
        try:
            return mqtt_subscribe.simple(topics, hostname=hostname, **mqtt_kwargs)

        except (ConnectionRefusedError, socket.gaierror) as e:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            # possible that leader is down/restarting, keep trying, but log to local machine.
            publish(
                "error_log",
                f"Attempt {retry}: Unable to connect to host: {hostname}. {str(e)}",
                hostname="localhost",
                retain=True,
            )
            print(f"{current_time}: Attempt {retry}: Unable to connect to host: {hostname}. {str(e)}")
            time.sleep(5 * retry)  # linear backoff
            retry += 1

        if retry == retries:
            current_time = time.strftime("%Y-%m-%d %H:%M:%S")
            raise ConnectionRefusedError(f"{current_time}: Unable to connect to host: {hostname}. Exiting.")


def subscribe_and_callback(callback, topics, hostname=leader_hostname, **mqtt_kwargs):
    """
    Creates a new thread, wrapping around paho's subscribe.callback
    TODO: what happens when I lose connection to host?
    """
    thread = threading.Thread(
        target=mqtt_subscribe.callback,
        kwargs={"callback": callback, "topics": topics, "hostname": hostname},  # TODO: wrap this and make error handling better.
        daemon=True,
    )
    thread.start()
