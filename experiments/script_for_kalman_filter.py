# -*- coding: utf-8 -*-

import json
import time

# from itertools import product
import numpy as np
import logging
from matplotlib import pyplot as plt

# import os.path

np.set_printoptions(suppress=True)
logging.disable(logging.WARNING)


from pioreactor.background_jobs.growth_rate_calculating import GrowthRateCalculator
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.pubsub import subscribe_and_callback, publish
from pioreactor.config import config
from pioreactor.whoami import get_unit_name

if __name__ == "__main__":

    unit = get_unit_name()
    interval_for_testing = 0.025
    config["od_config.od_sampling"]["samples_per_second"] = "0.2"

    for (ov, ac) in [(0.0005, 0.006)]:

        # if os.path.isfile(f"kalman_filter_exp/({av},{ov},{rv}).json"):
        #    print(f"skipping ({av},{ov},{rv})")
        #    continue

        exp = "testing_experiment"
        print(ov, ac)

        config["growth_rate_kalman"]["acc_variance"] = str(ac)
        config["growth_rate_kalman"]["obs_variance"] = str(ov)

        publish(
            f"pioreactor/{unit}/{exp}/growth_rate_calculating/growth_rate",
            None,
            retain=True,
        )
        publish(f"pioreactor/{unit}/{exp}/od_normalization/mean", None, retain=True)
        publish(f"pioreactor/{unit}/{exp}/od_normalization/variance", None, retain=True)

        start_time = time.time()
        od = ODReader(
            channel_label_map={"A0": "90/0", "A1": "90/1"},
            sampling_rate=interval_for_testing,
            unit=unit,
            experiment=exp,
            fake_data=True,
            stop_IR_led_between_ADC_readings=False,
        )
        calc = GrowthRateCalculator(unit=unit, experiment=exp)

        actual_grs = []
        estimated_grs = []

        def append_actual_growth_rates(msg):
            actual_grs.append(float(msg.payload))

        def append_estimated_growth_rates(msg):
            actual_grs.append(od.adc_reader.analog_in[0][1].gr)
            estimated_grs.append(float(msg.payload))

        c1 = subscribe_and_callback(
            append_actual_growth_rates, "pioreactor/mock/0/actual_gr"
        )
        c2 = subscribe_and_callback(
            append_estimated_growth_rates,
            f"pioreactor/{unit}/{exp}/growth_rate_calculating/growth_rate",
        )

        print("Generating data...")

        time.sleep(70)

        for i in range(30):
            time.sleep(7.5)

            publish(
                f"pioreactor/{unit}/{exp}/dosing_events",
                json.dumps(
                    {
                        "event": "add_media",
                        "volume_change": 1.0,
                        "source_of_event": "mock",
                    }
                ),
            )

        time.sleep(3)
        c1.loop_stop()
        c1.disconnect()

        c2.loop_stop()
        c2.disconnect()

        od.set_state("disconnected")
        calc.set_state("disconnected")

        plt.figure()
        plt.plot(np.arange(0, len(actual_grs)), actual_grs, label="actual_grs")
        plt.plot(np.arange(0, len(estimated_grs)), estimated_grs, label="estimated_grs")
        plt.title(f"obs_variance={ov},\nacc_variance={ac}")
        plt.tight_layout()
        print("saving fig...")
        plt.savefig(f"kalman_filter_exp/({ov},{ac}_with_dosing2).png")

        with open(f"kalman_filter_exp/({ov},{ac}).json", "w") as f:
            json.dump({"target": actual_grs, "estimated": estimated_grs}, f)
