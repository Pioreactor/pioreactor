# -*- coding: utf-8 -*-
from collections import defaultdict

from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.actions.led_intensity import led_intensity, CHANNELS
from pioreactor.whoami import get_latest_experiment_name, get_unit_name


def correlation(x, y):
    from statistics import stdev, mean

    mean_x, std_x = mean(x), stdev(x)
    mean_y, std_y = mean(y), stdev(y)

    if (std_y == 0) or (std_x == 0):
        return 0

    running_sum = 0
    running_count = 0
    for (x_, y_) in zip(x, y):
        running_sum += (x_ - mean_x) * (y_ - mean_y)
        running_count += 1

    return (running_sum / running_count) / std_y / std_x


if __name__ == "__main__":

    INTENSITIES = list(range(0, 105, 5))
    unit = get_unit_name()
    experiment = f"{get_latest_experiment_name()}-test"
    results = {}

    adc_reader = ADCReader(
        unit=unit, experiment=experiment, dynamic_gain=False, initial_gain=1
    )
    adc_reader.setup_adc()

    # set all to 0
    for channel in CHANNELS:
        led_intensity(
            channel, intensity=0, unit=unit, experiment=experiment, verbose=False
        )

    for channel in CHANNELS:
        varying_intensity_results = defaultdict(list)
        for intensity in INTENSITIES:
            # turn on the LED to set intensity
            led_intensity(
                channel,
                intensity=intensity,
                unit=unit,
                experiment=experiment,
                verbose=False,
            )

            # record from ADC
            adc_reader.take_reading()

            # Add to accumulating list
            varying_intensity_results["A0"].append(adc_reader.A0["voltage"])
            varying_intensity_results["A1"].append(adc_reader.A1["voltage"])
            varying_intensity_results["A2"].append(adc_reader.A2["voltage"])
            varying_intensity_results["A3"].append(adc_reader.A3["voltage"])
            print(
                f"Channel {channel} at {intensity}%. AO: {adc_reader.A0['voltage']}, A1: {adc_reader.A1['voltage']}, A2: {adc_reader.A2['voltage']}, A3: {adc_reader.A3['voltage']}"
            )

        # compute the linear correlation between the intensities and observed PD measurements
        results[("A0", channel)] = correlation(
            INTENSITIES, varying_intensity_results["A0"]
        )
        results[("A1", channel)] = correlation(
            INTENSITIES, varying_intensity_results["A1"]
        )

        results[("A2", channel)] = correlation(
            INTENSITIES, varying_intensity_results["A2"]
        )

        results[("A3", channel)] = correlation(
            INTENSITIES, varying_intensity_results["A3"]
        )

        # set back to 0
        led_intensity(
            channel, intensity=0, unit=unit, experiment=experiment, verbose=False
        )
        import time

        time.sleep(5)

    print(results)
