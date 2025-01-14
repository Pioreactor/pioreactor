# -*- coding: utf-8 -*-
# test_od_reading.py
from __future__ import annotations

import time

import numpy as np
import pytest

from pioreactor import exc
from pioreactor import structs
from pioreactor.background_jobs.od_reading import ADCReader
from pioreactor.background_jobs.od_reading import CachedCalibrationTransformer
from pioreactor.background_jobs.od_reading import NullCalibrationTransformer
from pioreactor.background_jobs.od_reading import ODReader
from pioreactor.background_jobs.od_reading import PhotodiodeIrLedReferenceTrackerStaticInit
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.config import temporary_config_change
from pioreactor.pubsub import collect_all_logs_of_level
from pioreactor.utils import local_persistent_storage
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.whoami import get_unit_name


def pause(n=1) -> None:
    time.sleep(n * 0.25)


def test_sin_regression_exactly_60hz() -> None:
    freq = 60
    N = 32
    C = 10.0
    A = 2.0
    phi = 1.0
    x = [i / N for i in range(N)]
    y = [C + A * np.sin(freq * 2 * np.pi * _x + phi) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C_, A_, phi_), _ = adc_reader._sin_regression_with_known_freq(x, y, freq)
    assert isinstance(A, float)
    assert isinstance(phi, float)
    assert C_ == pytest.approx(C, abs=0.15)
    assert A_ == pytest.approx(A, abs=0.15)
    assert phi_ == pytest.approx(phi, abs=0.15)


def test_sin_regression_exactly_50hz() -> None:
    freq = 50
    N = 32
    C = 10.0
    A = 2.0
    phi = 0.2
    x = [i / N for i in range(N)]
    y = [C + A * np.sin(freq * 2 * np.pi * _x + phi) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C_, A_, phi_), _ = adc_reader._sin_regression_with_known_freq(x, y, freq)
    assert isinstance(A, float)
    assert isinstance(phi, float)
    assert C_ == pytest.approx(C, abs=0.15)
    assert A_ == pytest.approx(A, abs=0.15)
    assert phi_ == pytest.approx(phi, abs=0.15)


def test_sin_regression_estimator_is_consistent() -> None:
    freq = 60

    N = 40_000
    C = 0.1
    A = 0.01
    phi = 1.0

    x = [i / N for i in range(N)]
    y = [C + A * np.sin(freq * 2 * np.pi * _x + phi) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C_, A_, phi_), _ = adc_reader._sin_regression_with_known_freq(x, y, freq)
    assert C_ == pytest.approx(C, rel=5e-2, abs=1e-3)
    assert A_ == pytest.approx(A, rel=5e-2, abs=1e-2)
    assert phi_ == pytest.approx(phi, rel=5e-2, abs=0.2)

    N = N * 4

    x = [i / N for i in range(N)]
    y = [C + A * np.sin(freq * 2 * np.pi * _x + phi) + 0.1 * np.random.randn() for _x in x]

    (C_, A_, phi_), _ = adc_reader._sin_regression_with_known_freq(x, y, freq)
    assert C_ == pytest.approx(C, rel=2.5e-2, abs=5e-4)
    assert A_ == pytest.approx(A, rel=2.5e-2, abs=5e-3)
    assert phi_ == pytest.approx(phi, rel=2.5e-2, abs=0.1)


def test_sin_regression_all_zeros_should_return_zeros() -> None:
    import numpy as np

    with np.errstate(all="raise"):
        adc_reader = ADCReader(channels=[])

        (C, A, phi), AIC = adc_reader._sin_regression_with_known_freq(
            [i / 25 for i in range(25)], [0] * 25, 60
        )
        assert C == 0
        assert A == 0
        assert np.isinf(AIC)


def test_sin_regression_real_data_and_that_60hz_is_the_minimum() -> None:
    y = [
        8694.0,
        8622.0,
        8587.0,
        8537.0,
        8533.0,
        8529.0,
        8556.0,
        8582.0,
        8698.0,
        8734.0,
        8841.0,
        8980.0,
        9005.0,
        9050.0,
        9077.0,
        9091.0,
        9107.0,
        9118.0,
        9102.0,
        9037.0,
        9006.0,
        8893.0,
        8855.0,
        8755.0,
        8597.0,
        8565.0,
    ]
    x = [
        6.849016062915325e-05,
        0.03225604514591396,
        0.06504625407978892,
        0.09745802800171077,
        0.13046979811042547,
        0.1631201640702784,
        0.19538412615656853,
        0.22827485506422818,
        0.2607731909956783,
        0.29389490908943117,
        0.3266107430681586,
        0.35897407913580537,
        0.39195163105614483,
        0.42453178903087974,
        0.45695877098478377,
        0.48978127096779644,
        0.5222139300312847,
        0.5552757519762963,
        0.5879572120029479,
        0.6202454441227019,
        0.6531873710919172,
        0.6857172690797597,
        0.7188976851757616,
        0.751680811168626,
        0.7840821680147201,
        0.8170840430539101,
    ]

    adc_reader = ADCReader(channels=[])
    (C, A, phi), AIC_60 = adc_reader._sin_regression_with_known_freq(x, y, 60)
    assert abs(C - np.mean(y)) < 10

    for i in range(2, 75):
        # skip i=32, noise
        if i == 32:
            continue

        (C, A, phi), AIC_i = adc_reader._sin_regression_with_known_freq(x, y, i)
        assert AIC_i >= AIC_60


def test_sin_regression_real_data_and_that_60hz_is_the_minimum2() -> None:
    y = [
        6393.0,
        6470.0,
        6523.0,
        6373.0,
        6375.0,
        6234.0,
        6147.0,
        6283.0,
        6264.0,
        6206.0,
        6276.0,
        6070.0,
        6047.0,
        6018.0,
        6162.0,
        6323.0,
        6044.0,
        5887.0,
        6100.0,
        6032.0,
        5988.0,
        6021.0,
        6043.0,
        6189.0,
        6299.0,
        6279.0,
    ]
    x = [
        0.011080539086833596,
        0.043024661019444466,
        0.07600112399086356,
        0.10825863108038902,
        0.14143993705511093,
        0.17404911015182734,
        0.2063259920105338,
        0.2390361011493951,
        0.2709076199680567,
        0.30479230894707143,
        0.337737939087674,
        0.3699464879464358,
        0.40293430513702333,
        0.4354570710565895,
        0.4678043171297759,
        0.5005605730693787,
        0.5329271419905126,
        0.5661279789637774,
        0.5986463711597025,
        0.6308952320832759,
        0.6638960181735456,
        0.6964425339829177,
        0.7295078509487212,
        0.7623454600106925,
        0.7947157791350037,
        0.8276583361439407,
    ]

    adc_reader = ADCReader(channels=[])
    (C, A, phi), AIC_60 = adc_reader._sin_regression_with_known_freq(x, y, 60)
    assert abs(C - np.mean(y)) < 10

    for i in range(2, 75):
        if i == 30 or i == 31 or i == 62:
            continue

        (C_, _, _), AIC_i = adc_reader._sin_regression_with_known_freq(x, y, i)

        assert AIC_i >= AIC_60, i


def test_sin_regression_constant_should_return_constant() -> None:
    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq([i / 25 for i in range(25)], [1.0] * 25, 60)
    assert C == 1.0
    assert abs(A - 0.0) < 1e-10  # type: ignore


def test_sin_regression_with_linear_change_should_return_close_to_mean() -> None:
    adc_reader = ADCReader(channels=[])

    y = [float(i) for i in range(25)]

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq([i / 25 for i in range(25)], y, 60)
    assert np.abs(C - np.mean(y)) < 0.001


def test_sin_regression_with_slightly_lower_frequency() -> None:
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 59.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C - 10) < 0.1


def test_sin_regression_with_slightly_higher_frequency_but_correct_freq_has_better_fit() -> None:
    # https://electronics.stackexchange.com/questions/57878/how-precise-is-the-frequency-of-the-ac-electricity-network
    actual_freq = 60.5

    x = [i / 25 for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C_60, A, phi), aic_60 = adc_reader._sin_regression_with_known_freq(x, y, 60)
    assert np.abs(C_60 - 10) < 0.1

    (C_61, A, phi), aic_61 = adc_reader._sin_regression_with_known_freq(x, y, actual_freq)
    assert aic_61 < aic_60  # lower is better


def test_sin_regression_with_strong_penalizer() -> None:
    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq(
        [i / 25 for i in range(25)], [100] * 25, 60, prior_C=125, penalizer_C=1_000_000
    )
    assert abs(C - 125) < 0.01


def test_ADC_picks_to_correct_freq() -> None:
    actual_freq = 50.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [10 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq

    actual_freq = 60.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [2 + np.sin(actual_freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq


def test_ADC_picks_to_correct_freq_even_if_slight_noise_in_freq() -> None:
    actual_freq = 50.0

    x = [i / 25 + 0.005 * np.random.randn() for i in range(25)]
    y = [10 + np.sin((actual_freq + 0.2) * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=["1"])

    best_freq = adc_reader.determine_most_appropriate_AC_hz({"1": x}, {"1": y})
    assert best_freq == actual_freq


def test_error_thrown_if_wrong_angle() -> None:
    with pytest.raises(ValueError):
        start_od_reading("100", "135", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("100", None, fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("135", "99", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    with pytest.raises(ValueError):
        start_od_reading("100", "REF", fake_data=True, experiment="test_error_thrown_if_wrong_angle")  # type: ignore

    st = start_od_reading("135", "90", fake_data=True, experiment="test_error_thrown_if_wrong_angle")
    st.clean_up()


def test_sin_regression_penalizer_C_is_independent_of_scale_of_observed_values() -> None:
    freq = 60
    C_True = 10
    x = [i / 25 for i in range(25)]
    y = [C_True + 2 * np.sin(freq * 2 * np.pi * _x) + 0.1 * np.random.randn() for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq(x, y, freq, prior_C=12, penalizer_C=10.0)
    ratio = C / C_True

    # scale everything by 10
    factor = 10
    y = [factor * y_ for y_ in y]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), _ = adc_reader._sin_regression_with_known_freq(
        x, y, freq, prior_C=factor * 12, penalizer_C=10.0
    )
    assert np.abs(C / (factor * C_True) - ratio) < 0.01


def test_sin_regression_all_negative() -> None:
    freq = 60
    x = [i / 25 for i in range(25)]
    y = [-2.0 for _x in x]

    adc_reader = ADCReader(channels=[])

    (C, A, phi), AIC = adc_reader._sin_regression_with_known_freq(x, y, freq)
    assert C == -2
    assert AIC == float("inf")


def test_simple_API() -> None:
    od_job = start_od_reading("90", "REF", interval=100_000, fake_data=True)

    for led_int in range(5, 70, 15):
        time.sleep(2)
        od_job.ir_led_intensity = led_int
        od_job.start_ir_led()
        assert od_job.ir_led_intensity == led_int
        results = od_job.record_from_adc()
        assert list(results.ods.keys()) == ["1"]

    od_job.clean_up()


def test_ability_to_be_iterated() -> None:
    od_stream = start_od_reading(
        "90",
        "REF",
        interval=1.0,
        fake_data=True,
        experiment="test_ability_to_be_iterated",
    )
    results = []

    for i, reading in enumerate(od_stream):
        results.append(reading)
        if i == 5:
            break

    assert len(results) > 0
    assert results[0].timestamp < results[1].timestamp < results[2].timestamp
    assert results[-1] == od_stream.ods
    assert od_stream.od1 == od_stream.ods.ods["1"]
    od_stream.clean_up()


def test_add_pre_read_callback() -> None:
    def cb(od_job):
        od_job.ir_led_intensity = 15

    ODReader.add_pre_read_callback(cb)

    od = start_od_reading("45", "REF", interval=1, fake_data=True)
    pause()
    pause()
    pause()
    pause()
    assert od.ir_led_intensity == 15
    od.clean_up()

    # clear it again.
    ODReader._pre_read.clear()


def test_add_post_read_callback() -> None:
    def cb(self, batched_readings, *args):
        self.logger.critical(f"{batched_readings=}")

    ODReader.add_post_read_callback(cb)

    with collect_all_logs_of_level(
        "CRITICAL", experiment="test_add_post_read_callback", unit="test"
    ) as bucket:
        od = start_od_reading(
            "45",
            "REF",
            interval=1,
            fake_data=True,
            experiment="test_add_post_read_callback",
            unit="test",
        )
        pause(25)
        od.clean_up()
        assert len(bucket) > 0

    # clear it again.
    ODReader._post_read.clear()


def test_outliers_are_removed_in_sin_regression() -> None:
    freq = 60
    x = [
        6.973999552428722e-05,
        0.03355777799151838,
        0.06766039799549617,
        0.1013846330170054,
        0.13573287799954414,
        0.1696973209909629,
        0.2032879629987292,
        0.23748631199123338,
        0.27130481801577844,
        0.3057407700107433,
        0.33978755699354224,
        0.373446949000936,
        0.40773284900933504,
        0.4416320839955006,
        0.4753085080010351,
        0.5095541480113752,
        0.5434022890112828,
        0.5778828249895014,
        0.6119594550109468,
        0.6456623889971524,
        0.679938810004387,
        0.7139212219917681,
        0.7484785279957578,
        0.7826525020063855,
        0.8165176229958888,
    ]
    adc_reader = ADCReader(channels=[])

    y_with_outlier = [
        11321.0,
        249.0,
        180.0,
        123.0,
        160.0,
        125.0,
        59.0,
        96.0,
        105.0,
        177.0,
        213.0,
        184.0,
        237.0,
        264.0,
        304.0,
        325.0,
        295.0,
        307.0,
        295.0,
        396.0,
        336.0,
        252.0,
        207.0,
        118.0,
        100.0,
    ]
    (C1, A, phi), _ = adc_reader._sin_regression_with_known_freq(x, y_with_outlier, freq)

    y_without_outlier = [
        211.0,
        249.0,
        180.0,
        123.0,
        160.0,
        125.0,
        59.0,
        96.0,
        105.0,
        177.0,
        213.0,
        184.0,
        237.0,
        264.0,
        304.0,
        325.0,
        295.0,
        307.0,
        295.0,
        396.0,
        336.0,
        252.0,
        207.0,
        118.0,
        100.0,
    ]
    (C2, A, phi), _ = adc_reader._sin_regression_with_known_freq(x, y_without_outlier, freq)

    assert np.abs(C1 - C2) < 5


def test_interval_is_empty() -> None:
    with start_od_reading("90", "REF", interval=None, fake_data=True) as od:
        assert not hasattr(od, "record_from_adc_timer")


def test_determine_best_ir_led_intensity_values() -> None:
    _determine_best_ir_led_intensity = ODReader._determine_best_ir_led_intensity

    assert (
        _determine_best_ir_led_intensity(
            {"2": "90"},
            50,
            {"1": 0.05, "2": 0.02},  # on
            {"1": 0.001, "2": 0.001},  # blank
        )
        == 80.0
    )

    assert (
        _determine_best_ir_led_intensity(
            {"2": "90"},
            50,
            {"1": 0.2, "2": 0.02},  # on
            {"1": 0.001, "2": 0.001},  # blank
        )
        == 60.0
    )

    assert (
        _determine_best_ir_led_intensity(
            {"2": "90"},
            50,
            {"1": 0.2, "2": 0.5},  # on
            {"1": 0.001, "2": 0.001},  # blank
        )
        == 6.0
    )


def test_calibration_not_requested() -> None:
    with start_od_reading("90", "REF", interval=None, fake_data=True) as od:
        assert isinstance(od.calibration_transformer, NullCalibrationTransformer)
        assert od.calibration_transformer({"2": 0.1}) == {"2": 0.1}
        assert od.calibration_transformer({"2": 0.5, "1": 0.0}) == {"2": 0.5, "1": 0.0}


def test_calibration_not_present() -> None:
    with local_persistent_storage("active_calibrations") as c:
        c.pop("od")

    cal = load_active_calibration("od")

    with start_od_reading("90", "REF", interval=None, fake_data=True, calibration=cal) as od:
        assert isinstance(od.calibration_transformer, NullCalibrationTransformer)
        assert len(od.calibration_transformer.models) == 0, od.calibration_transformer.models


def test_calibration_simple_linear_calibration_positive_slope() -> None:
    experiment = "test_calibration_simple_linear_calibration_positive_slope"

    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[2.0, 0.0],
        calibration_name="linear",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 2], "y": [0, 1]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF",
        "90",
        interval=None,
        fake_data=True,
        experiment=experiment,
        unit=get_unit_name(),
        calibration=cal,
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)

        voltage = 0.0
        assert od.calibration_transformer.models["2"](voltage) == (voltage - 0) / 2

        voltage = 0.5
        assert od.calibration_transformer.models["2"](voltage) == (voltage - 0) / 2
        pause()
        pause()
        pause()
        with collect_all_logs_of_level("warning", unit=get_unit_name(), experiment="+") as bucket:
            pause()
            pause()
            pause()
            voltage = 10.0
            assert od.calibration_transformer.models["2"](voltage) == 1.0
            pause()
            pause()
            pause()
            assert "Signal outside" in bucket[0]["message"]


def test_calibration_simple_linear_calibration_negative_slope() -> None:
    experiment = "test_calibration_simple_linear_calibration_negative_slope"
    maximum_voltage = 5.0
    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[-0.1, 2],
        calibration_name="linear",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"y": [0, maximum_voltage], "x": [0, 20]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF",
        "90",
        interval=None,
        fake_data=True,
        experiment=experiment,
        unit=get_unit_name(),
        calibration=cal,
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)

        voltage = 0.0
        assert od.calibration_transformer.models["2"](voltage) == (voltage - 2) / (-0.1)

        voltage = 0.5
        assert od.calibration_transformer.models["2"](voltage) == (voltage - 2) / (-0.1)

        with collect_all_logs_of_level("warning", unit=get_unit_name(), experiment="+") as bucket:
            voltage = 12.0
            assert voltage > maximum_voltage

            pause()
            assert od.calibration_transformer.models["2"](voltage) == 0.0
            pause()
            pause()
            assert "suggested" in bucket[0]["message"]


def test_calibration_simple_quadratic_calibration() -> None:
    experiment = "test_calibration_simple_quadratic_calibration"

    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[1.0, 0, -0.1],
        calibration_name="quad_test",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 1], "y": [0, 2]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF",
        "90",
        interval=None,
        fake_data=True,
        experiment=experiment,
        unit=get_unit_name(),
        calibration=cal,
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)
        x = 0.5
        assert abs(od.calibration_transformer.models["2"](x) - np.sqrt(3 / 5)) < 0.001


def test_calibration_multi_modal() -> None:
    experiment = "test_calibration_multi_modal"
    # note: not a realistic calibration curve, using only because it's unimodal
    poly = [0.2983, -0.585, 0.146, 0.261, 0.0]  # unimodal, peak near ~(0.74, 0.120)

    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=poly,
        calibration_name="multi_test",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 1], "y": [0, 2]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF", "90", interval=None, fake_data=True, experiment=experiment, calibration=cal
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)
        for i in range(0, 1000):
            voltage = np.polyval(poly, i / 1000)
            print(voltage, od.calibration_transformer.models["2"](voltage))


def test_calibration_errors_when_ir_led_differs() -> None:
    experiment = "test_calibration_errors_when_ir_led_differs"

    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "100"):
        cal = structs.ODCalibration(
            created_at=current_utc_datetime(),
            curve_type="poly",
            curve_data_=[1.0, 0, -0.1],
            calibration_name="quad_test",
            ir_led_intensity=50.0,
            angle="90",
            recorded_data={"x": [0, 1], "y": [0, 2]},
            pd_channel="2",
            calibrated_on_pioreactor_unit=get_unit_name(),
        )

        cal.set_as_active_calibration_for_device("od")
        with pytest.raises(exc.CalibrationError) as error:
            with start_od_reading(
                "REF", "90", interval=1, fake_data=True, experiment=experiment, calibration=cal
            ):
                pass
        assert "LED intensity" in str(error.value)


def test_calibration_with_irl_data1() -> None:
    MAX_OD = 1.131
    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=[
            0.13015369282405273,
            -0.49893265063642067,
            0.6953041334198933,
            0.45652927538964966,
            0.0024870149666305712,
        ],
        calibration_name="quad_test",
        ir_led_intensity=70.0,
        angle="90",
        recorded_data={
            "x": [
                0.030373011520747333,
                0.0678711757682291,
                0.12972798681328354,
                0.2663836655898364,
                0.4248479170421593,
                0.5921451667865667,
                0.8995772568778957,
                0.001996680972202709,
            ],
            "y": [0.042, 0.108, 0.237, 0.392, 0.585, 0.781, MAX_OD, 0.0],
        },
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    cc = CachedCalibrationTransformer()
    cc.hydate_models(cal)
    assert cc({"2": 0.001})["2"] == 0
    assert cc({"2": 0.002})["2"] == 0
    assert abs(cc({"2": 0.004})["2"] - 0.0032975807375385234) < 1e-5
    assert abs(cc({"2": 0.020})["2"] - 0.03639585015289039) < 1e-5
    assert cc({"2": 1.0})["2"] == MAX_OD


def test_PhotodiodeIrLedReferenceTrackerStaticInit() -> None:
    tracker = PhotodiodeIrLedReferenceTrackerStaticInit(channel="1")

    for i in range(1000):
        v = 0.001 * np.random.randn() + 0.25
        tracker.update(v)

    assert abs(tracker.led_output_ema.get_latest() - 0.25) < 0.01
    assert abs(tracker.led_output_emstd.get_latest() - 0.001) < 0.01

    # normalize a value
    assert abs(tracker.transform(1.0) - 4.0) < 0.1

    for i in range(100):
        v = 0.001 * np.random.randn() + 0.50  # a bump in IR
        tracker.update(v)


def test_ODReader_with_multiple_angles_and_a_ref() -> None:
    """
    Technically not possible, since there are only two PD channels.

    """
    experiment = "test_ODReader_with_multiple_angles_and_a_ref"

    ir_led_reference_channel = "version"  # hack
    channel_angle_map = {"1": "45", "2": "90"}
    channels = ["1", "2", ir_led_reference_channel]

    # use IR LED reference to normalize?
    ir_led_reference_tracker = PhotodiodeIrLedReferenceTrackerStaticInit(
        ir_led_reference_channel,  # type: ignore
    )

    with ODReader(
        channel_angle_map,  # type: ignore
        interval=3,
        unit=get_unit_name(),
        experiment=experiment,
        adc_reader=ADCReader(channels=channels, fake_data=True, dynamic_gain=False),  # type: ignore
        ir_led_reference_tracker=ir_led_reference_tracker,
        calibration_transformer=NullCalibrationTransformer(),
    ) as odr:
        for i, signal in enumerate(odr):
            print(signal)
            if i == 3:
                break


def test_calibration_data_from_user1() -> None:
    # the problem is that the 4th degree polynomial doesn't always have a solution to the inverse problem.
    experiment = "test_calibration_data_from_user1"
    poly = [2.583, -3.447, 1.531, 0.223, 0.017]  # email correspondence

    calibration = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=poly,
        calibration_name="multi_test",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 10], "y": [0, 10]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    calibration.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF", "90", interval=None, fake_data=True, experiment=experiment, calibration=calibration
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)
        infer = od.calibration_transformer.models["2"]

        # try varying voltage up over and across the lower bound, and assert we are always non-decreasing.
        od_0 = 0
        for i in range(10):
            voltage = i / 5 + 0.1

            od_1 = infer(voltage)
            assert od_0 <= od_1
            od_0 = od_1


def test_calibration_data_from_user2() -> None:
    # the difference here is that the 3 degree polynomial always has a solution to the inverse problem.
    experiment = "test_calibration_data_from_user2"
    poly = [
        1.71900012,
        -1.77900665,
        0.95000656,
        -0.01770485,
    ]  # looks like the degree 4 above: https://chat.openai.com/share/2ef30900-22ef-4a7f-8f34-14a88ffc65a8

    cal = structs.ODCalibration(
        created_at=current_utc_datetime(),
        curve_type="poly",
        curve_data_=poly,
        calibration_name="multi_test",
        ir_led_intensity=90.0,
        angle="90",
        recorded_data={"x": [0, 10], "y": [0, 10]},
        pd_channel="2",
        calibrated_on_pioreactor_unit=get_unit_name(),
    )

    cal.set_as_active_calibration_for_device("od")

    with start_od_reading(
        "REF", "90", interval=None, fake_data=True, experiment=experiment, calibration=cal
    ) as od:
        assert isinstance(od.calibration_transformer, CachedCalibrationTransformer)
        infer = od.calibration_transformer.models["2"]

        # try varying voltage up over and across the lower bound, and assert we are always non-decreasing.
        od_0 = 0
        for i in range(10):
            voltage = i / 5 * 0.018
            od_1 = infer(voltage)
            assert od_0 <= od_1
            od_0 = od_1


def test_auto_ir_led_intensit_REF_and_90() -> None:
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "auto"):
        experiment = "test_auto_ir_led_intensity"

        with start_od_reading("REF", "90", interval=None, fake_data=True, experiment=experiment) as od:
            assert abs(od.ir_led_intensity - 67.19794921875) < 0.01


def test_auto_ir_led_intensity_90_only() -> None:
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "auto"):
        experiment = "test_auto_ir_led_intensity"

        with start_od_reading(None, "90", interval=None, fake_data=True, experiment=experiment) as od:
            assert od.ir_led_intensity == 70.0


def test_auto_ir_led_intensity_90_and_90() -> None:
    with temporary_config_change(config, "od_reading.config", "ir_led_intensity", "auto"):
        experiment = "test_auto_ir_led_intensity"

        with start_od_reading("90", "90", interval=None, fake_data=True, experiment=experiment) as od:
            assert od.ir_led_intensity == 70.0


def test_at_least_one_channel() -> None:
    experiment = "test_at_least_one_channel"

    with pytest.raises(ValueError):
        with start_od_reading(None, None, interval=None, fake_data=True, experiment=experiment):
            pass


def test_at_least_one_signal_channel() -> None:
    experiment = "test_at_least_one_signal_channel"

    with pytest.raises(ValueError):
        with start_od_reading("REF", None, interval=None, fake_data=True, experiment=experiment):
            pass


def test_CachedCalibrationTransformer_with_real_calibration() -> None:
    calibration = structs.ODCalibration(
        angle="90",
        curve_type="poly",
        curve_data_=[
            -0.9876751958847302,
            1.2023377416112089,
            0.2591472668916862,
            0.8385902257553322,
            0.0445071255201746,
        ],
        ir_led_intensity=50,
        pd_channel="2",
        created_at=current_utc_datetime(),
        calibrated_on_pioreactor_unit="pio1",
        recorded_data={
            "y": [
                1.359234153183015,
                1.1302469550069834,
                0.9620188870414657,
                0.8276740491499182,
                0.7190293946984384,
                0.7476589503369395,
                0.566173065500996,
                0.46932081671790027,
                0.40529520650943107,
                0.35571051870062176,
                0.3671813602478582,
                0.30365395611828694,
                0.2546057746249075,
                0.22793433386962852,
                0.20673156637999296,
                0.21349869357483414,
                0.182990681059356,
                0.15688343308939462,
                0.1576635057554899,
                0.12760694773293027,
                0.1334217593444793,
                0.12112005296098335,
                0.10527636587260703,
                0.10005326421654448,
                0.08968165025432195,
                0.0934433078631241,
                0.08568480676160387,
                0.07354768447704799,
                0.07012049853534189,
                0.06976807020449396,
                0.0692776692431696,
                0.06519934195388995,
                0.05689993752281371,
                0.06139548846791462,
                0.05434995401134063,
                0.058377357520436435,
                0.05744855604656168,
                0.051622250927144994,
                0.04809794996045024,
                0.044709852782465254,
            ],
            "x": [
                1.0,
                0.8333333333333334,
                0.7142857142857143,
                0.625,
                0.5555555555555556,
                0.58,
                0.48333333333333334,
                0.41428571428571426,
                0.3625,
                0.3222222222222222,
                0.3,
                0.25,
                0.21428571428571427,
                0.1875,
                0.16666666666666666,
                0.18,
                0.15,
                0.12857142857142856,
                0.11249999999999999,
                0.09999999999999999,
                0.1,
                0.08333333333333333,
                0.07142857142857142,
                0.0625,
                0.05555555555555555,
                0.065,
                0.05416666666666667,
                0.04642857142857143,
                0.040625,
                0.036111111111111115,
                0.04,
                0.03333333333333333,
                0.028571428571428574,
                0.025,
                0.022222222222222223,
                0.03,
                0.024999999999999998,
                0.02142857142857143,
                0.01875,
                0.0,
            ],
        },
        calibration_name="test",
    )
    calibration.save_to_disk_for_device("od")

    calibration.set_as_active_calibration_for_device("od")

    cal_transformer = CachedCalibrationTransformer()
    cal_transformer.hydate_models(calibration)

    assert abs(cal_transformer({"2": 0.096})["2"] - 0.06) < 0.01


def test_missing_calibration_data():
    cal_transformer = CachedCalibrationTransformer()
    cal_transformer.models = {"1": lambda v: v * 2}
    assert cal_transformer({"1": 1.0, "2": 2.0}) == {"1": 2.0, "2": 2.0}
