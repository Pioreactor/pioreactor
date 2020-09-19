# -*- coding: utf-8 -*-
"""
Continuously monitor the bioreactor and provide summary statistics on what's going on
"""
import json
import traceback

import paho.mqtt.subscribe as paho_subscribe
import click

from morbidostat.utils.pubsub import publish, subscribe
from morbidostat.utils import leader_hostname, get_unit_from_hostname, killables


VIAL_VOLUME = 12


class AltMediaCalculator:
    """
    Computes the fraction of the vial that is from the alt-media vs the regular media.

    Parameters
    -----------
    ignore_cache: ignore any retained values in the MQTT bus
    """

    def __init__(self, unit=None, ignore_cache=False, verbose=False, **kwargs):
        self.unit = unit
        self.ignore_cache = ignore_cache
        self.verbose = verbose

    @property
    def latest_alt_media_fraction(self):
        if hasattr(self, "_latest_alt_media_fraction"):
            return self._latest_alt_media_fraction
        elif self.ignore_cache:
            self._latest_alt_media_fraction = 0
        else:
            try:
                msg = subscribe(f"morbidostat/{self.unit}/alt_media_fraction", keepalive=10)
                self._latest_alt_media_fraction = float(msg.payload)
            except:
                self._latest_alt_media_fraction = 0
        return self._latest_alt_media_fraction

    @latest_alt_media_fraction.setter
    def latest_alt_media_fraction(self, value):
        self._latest_alt_media_fraction = value

    def on_message(self, client, userdata, message):
        try:
            assert message.topic == f"morbidostat/{self.unit}/io_events"
            payload = json.loads(message.payload)
            volume, event = float(payload["volume_change"]), payload["event"]
            if event == "add_media":
                self.update_alt_media_fraction(volume, 0)
            elif event == "add_alt_media":
                self.update_alt_media_fraction(0, volume)
            elif event == "remove_waste":
                pass
            else:
                raise ValueError()
        except:
            # paho swallows exceptions in callbacks, this spits them back up.
            traceback.print_exc()
            return

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

        publish(f"morbidostat/{self.unit}/alt_media_fraction", self.latest_alt_media_fraction, verbose=self.verbose, retain=True)

        return


@click.command()
@click.option("--ignore_cache", is_flag=True, help="ignore the retained MQTT msg")
@click.option("--verbose", is_flag=True, help="print to std.out")
def io_listening(ignore_cache, verbose):
    unit = get_unit_from_hostname()
    publish(f"morbidostat/{unit}/log", f"[io_listening]: starting", verbose=verbose)

    paho_subscribe.callback(
        AltMediaCalculator(unit=unit, ignore_cache=ignore_cache, verbose=verbose).on_message,
        f"morbidostat/{unit}/io_events",
        hostname=leader_hostname,
    )


if __name__ == "__main__":
    io_listening()
