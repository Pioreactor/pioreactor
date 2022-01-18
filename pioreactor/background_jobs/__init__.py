# -*- coding: utf-8 -*-

# needed to import to "load" the automation subclasses,
# and hence the *-controller will register them.
from pioreactor.automations import *  # noqa: F401,F403

from pioreactor.background_jobs import growth_rate_calculating
from pioreactor.background_jobs import dosing_control
from pioreactor.background_jobs import led_control
from pioreactor.background_jobs import temperature_control
from pioreactor.background_jobs import od_reading
from pioreactor.background_jobs import stirring
from pioreactor.background_jobs import monitor
from pioreactor.background_jobs.leader import mqtt_to_db_streaming
from pioreactor.background_jobs.leader import watchdog


__all__ = (
    "monitor",
    "mqtt_to_db_streaming",
    "watchdog",
    "growth_rate_calculating",
    "dosing_control",
    "led_control",
    "temperature_control",
    "od_reading",
    "stirring",
)
