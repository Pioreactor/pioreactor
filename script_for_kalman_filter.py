# -*- coding: utf-8 -*-

import json
import time
from itertools import product
import numpy as np
import logging
from matplotlib import pyplot as plt
import os.path


logging.disable(logging.WARNING)


from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.pubsub import subscribe_and_callback, publish
from pioreactor.config import config


unit = "unit"
interval_for_testing = 0.020
config["od_config.od_sampling"]["samples_per_second"] = "0.2"

for rv, ov, av in product(
    np.logspace(-2, -6, 5), np.logspace(-2, -6, 5), np.logspace(-2, -6, 5)
):

    if os.path.isfile(f"kalman_filter_exp/({av},{ov},{rv}).json"):
        print(f"skipping ({av},{ov},{rv})")
        continue

    exp = f"({av},{ov},{rv})"
    print(rv, ov, av)

    config["growth_rate_kalman"]["rate_variance"] = str(rv)  # 0.00300
    config["growth_rate_kalman"]["obs_variance"] = str(ov)  # 0.00015
    config["growth_rate_kalman"]["acc_variance"] = str(av)  # 0.00050

    publish(f"pioreactor/{unit}/{exp}/growth_rate", None, retain=True)

    od = ODReader(
        channel_label_map={"A0": "90/0", "A1": "90/1"},
        sampling_rate=interval_for_testing,
        unit=unit,
        experiment=exp,
        fake_data=True,
        stop_IR_led_between_ADC_readings=False,
    )
    st = Stirrer(duty_cycle=0, unit=unit, experiment=exp)
    calc = GrowthRateCalculator(unit=unit, experiment=exp)

    actual_grs = []
    estimated_grs = []

    def append_actual_growth_rates(msg):
        actual_grs.append(float(msg.payload))

    def append_estimated_growth_rates(msg):
        estimated_grs.append(float(msg.payload))

    c1 = subscribe_and_callback(append_actual_growth_rates, "pioreactor/mock/0/actual_gr")
    c2 = subscribe_and_callback(
        append_estimated_growth_rates, f"pioreactor/{unit}/{exp}/growth_rate"
    )

    print("Generating data...")

    time.sleep(180)

    publish(
        f"pioreactor/{unit}/{exp}/dosing_events",
        json.dumps(
            {"event": "add_media", "volume_change": 1.0, "source_of_event": "mock"}
        ),
    )

    time.sleep(40)

    c1.loop_stop()
    c1.disconnect()

    c2.loop_stop()
    c2.disconnect()

    od.set_state("disconnected")
    st.set_state("disconnected")
    calc.set_state("disconnected")

    plt.figure()
    plt.plot(np.arange(0, len(actual_grs)), actual_grs, label="actual_grs")
    plt.plot(np.arange(0, len(estimated_grs)), estimated_grs, label="estimated_grs")
    plt.title(f"acc_variance={av},\nobs_variance={ov},\nrate_variance={rv}")
    plt.tight_layout()
    print("saving fig...")
    plt.savefig(f"kalman_filter_exp/({av},{ov},{rv}).png")

    with open(f"kalman_filter_exp/({av},{ov},{rv}).json", "w") as f:
        json.dump({"target": actual_grs, "estimated": estimated_grs}, f)
