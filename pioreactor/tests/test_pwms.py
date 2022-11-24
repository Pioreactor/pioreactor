# -*- coding: utf-8 -*-
# test_pwms
from __future__ import annotations

import json
import time

from pioreactor import pubsub
from pioreactor.utils.pwm import PWM
from pioreactor.whoami import get_unit_name


def pause(n=1) -> None:
    time.sleep(n * 0.25)


def test_pwm_update_mqtt():
    exp = "test_pwm_update_mqtt"
    unit = get_unit_name()

    mqtt_items = []

    def collect(msg) -> None:
        mqtt_items.append(msg.payload.decode())

    pubsub.subscribe_and_callback(collect, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)

    pwm12 = PWM(12, 10, experiment=exp, unit=unit)
    pwm12.lock()
    pwm12.start(50)
    pwm12.change_duty_cycle(20)
    pwm12.cleanup()
    pause()

    assert len(mqtt_items) == 3
    assert json.loads(mqtt_items[0])["12"] == 50.0
    assert json.loads(mqtt_items[1])["12"] == 20.0
    assert json.loads(mqtt_items[2])["12"] == 0.0


def test_pwm_update_mqtt_multiple_at_one():
    exp = "test_pwm_update_mqtt"
    unit = get_unit_name()

    mqtt_items = []

    def collect(msg) -> None:
        mqtt_items.append(msg.payload.decode())

    pubsub.subscribe_and_callback(collect, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)

    pwm12 = PWM(12, 10, experiment=exp, unit=unit)
    pwm12.lock()
    pwm12.start(50)

    pwm17 = PWM(17, 10, experiment=exp, unit=unit)
    pwm17.lock()
    pwm17.start(34)
    pwm17.change_duty_cycle(20)

    pwm17.cleanup()
    pwm12.cleanup()

    pause()

    assert len(mqtt_items) == 5
    assert json.loads(mqtt_items[0])["12"] == 50.0
    assert json.loads(mqtt_items[0]).get("17", 0.0) == 0.0

    assert json.loads(mqtt_items[1]).get("17", 0.0) == 34.0
    assert json.loads(mqtt_items[1]).get("12", 0.0) == 50.0

    assert json.loads(mqtt_items[-1]).get("17", 0.0) == 0.0
    assert json.loads(mqtt_items[-1]).get("12", 0.0) == 0.0
