"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""
import json

import paho.mqtt.subscribe as subscribe
import click
import board
import busio

from morbidostat.utils.pubishing import publish
from morbidostat.utils import leader_hostname


VIAL_VOLUME = 12


class AltMediaCalculator:
    def __init__(self, unit=None, **kwargs):
        self.unit = unit

    @property
    def latest_alt_media_fraction(self):
        if hasattr(self, "_latest_alt_media_fraction"):
            return self._latest_alt_media_fraction
        else:
            try:
                msg = subscribe.simple(
                    f"morbidostat/{self.unit}/alt_media_fraction",
                    keepalive=10,
                    hostname=leader_hostname,
                )
                self._latest_alt_media_fraction = float(msg.payload)
            except:
                self._latest_alt_media_fraction = 0
            return self._latest_alt_media_fraction

    @latest_alt_media_fraction.setter
    def latest_alt_media_fraction(self, value):
        self._latest_alt_media_fraction = value

    def on_message(self, client, userdata, message):
        assert message.topic == f"morbidostat/{self.unit}/io_events"

        payload = json.loads(message.payload)
        volume, event = float(payload["volume"]), payload["event"]
        if event == "add_media":
            self.update_alt_media_fraction(volume, 0)
        elif event == "add_alt_media":
            self.update_alt_media_fraction(0, volume)
        elif event == "remove_waste":
            pass
        else:
            raise ValueError()

    def update_alt_media_fraction(self, media_delta, alt_media_delta):
        total_delta = media_delta + alt_media_delta

        # current mL
        alt_media_ml = VIAL_VOLUME * self.latest_alt_media_fraction
        media_ml = VIAL_VOLUME * (1 - self.latest_alt_media_fraction)

        # remove
        alt_media_ml = alt_media_ml * (1 - total_delta / VIAL_VOLUME)
        media_ml = media_ml * (1 - total_delta / VIAL_VOLUME)

        # add (alt) media
        alt_media_ml = alt_media_ml + alt_media_delta
        media_ml = media_ml + media_delta

        self.latest_alt_media_fraction = alt_media_ml / VIAL_VOLUME

        publish(
            f"morbidostat/{self.unit}/alt_media_fraction",
            self.latest_alt_media_fraction,
            retain=True,
        )

        return


@click.command()
@click.option("--unit", default="1", help="The morbidostat unit")
def io_listening(mode, target_od, unit, duration, volume):

    publish(f"morbidostat/{unit}/log", f"starting io_listening")

    subscribe.callback(
        AltMediaCalculator(unit).on_message,
        f"morbidostat/{unit}/io_events",
        hostname=leader_hostname,
    )


if __name__ == "__main__":
    io_controlling()
