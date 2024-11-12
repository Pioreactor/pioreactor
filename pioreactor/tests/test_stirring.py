# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time

from pioreactor.background_jobs.stirring import RpmCalculator
from pioreactor.background_jobs.stirring import RpmFromFrequency
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.utils import local_persistant_storage
from pioreactor.utils.mock import MockRpmCalculator
from pioreactor.utils.timing import catchtime
from pioreactor.whoami import get_unit_name

unit = get_unit_name()


def pause(n=1) -> None:
    # to avoid race conditions
    time.sleep(n * 0.5)


def test_stirring_runs() -> None:
    st = start_stirring(target_rpm=500)
    assert st.duty_cycle > 0
    st.clean_up()


def test_change_target_rpm_mid_cycle() -> None:
    original_rpm = 500
    exp = "test_change_target_rpm_mid_cycle"

    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()

    with Stirrer(original_rpm, unit, exp, rpm_calculator=rpm_calculator) as st:
        st.start_stirring()
        assert st.target_rpm == original_rpm
        pause()

        new_rpm = 750
        publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", new_rpm)
        pause()

        assert st.target_rpm == new_rpm
        assert st.state == "ready"

        publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", 0)
        pause()
        assert st.target_rpm == 0


def test_pause_stirring_mid_cycle() -> None:
    exp = "test_pause_stirring_mid_cycle"
    with Stirrer(500, unit, exp, rpm_calculator=None) as st:
        assert st.duty_cycle == 0
        st.start_stirring()
        original_dc = st.duty_cycle
        assert original_dc > 0
        pause()

        publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "sleeping")
        pause()
        pause()
        pause()
        assert st.state == st.SLEEPING
        assert st.duty_cycle == 0

        publish(f"pioreactor/{unit}/{exp}/stirring/$state/set", "ready")
        pause()
        pause()
        pause()
        assert st.state == st.READY
        assert st.duty_cycle == original_dc


def test_publish_target_rpm() -> None:
    exp = "test_publish_target_rpm"
    publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm", None, retain=True)
    pause()
    target_rpm = 500
    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()
    with Stirrer(target_rpm, unit, exp, rpm_calculator=rpm_calculator) as st:
        st.start_stirring()
        assert st.target_rpm == target_rpm

        pause()
        message = subscribe(f"pioreactor/{unit}/{exp}/stirring/target_rpm")
        assert message is not None
        assert float(message.payload) == 500


def test_publish_measured_rpm() -> None:
    exp = "test_publish_measured_rpm"

    publish(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", None, retain=True)
    pause()

    target_rpm = 500
    rpm_calculator = RpmFromFrequency()
    rpm_calculator.setup()
    with Stirrer(target_rpm, unit, exp, rpm_calculator=rpm_calculator) as st:
        st.start_stirring()
        assert st.target_rpm == target_rpm

        pause(22)

        message = subscribe(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", timeout=3)
        assert message is not None
        assert json.loads(message.payload)["measured_rpm"] == 0


def test_rpm_isnt_updated_if_there_is_no_rpm_measurement() -> None:
    exp = "test_publish_measured_rpm"

    publish(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", None, retain=True)
    pause()

    target_rpm = 500

    with Stirrer(target_rpm, unit, exp, rpm_calculator=None) as st:
        st.start_stirring()
        assert st.target_rpm is None

        pause(22)

        message = subscribe(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", timeout=1)
        assert message is None


def test_stirring_with_lookup_linear_v1() -> None:
    exp = "test_stirring_with_lookup_linear_v1"

    class FakeRpmCalculator:
        def setup(self):
            return

        def __call__(self, *args):
            return 475

        def clean_up(self):
            pass

    with local_persistant_storage("stirring_calibration") as cache:
        cache["linear_v1"] = json.dumps({"rpm_coef": 0.1, "intercept": 20})

    target_rpm = 500
    rpm_calculator = FakeRpmCalculator()
    rpm_calculator.setup()
    with Stirrer(target_rpm, unit, exp, rpm_calculator=rpm_calculator) as st:  # type: ignore
        st.start_stirring()

        current_dc = st.duty_cycle
        target_rpm = 600
        publish(f"pioreactor/{unit}/{exp}/stirring/target_rpm/set", target_rpm)
        pause()
        pause()

        assert st.duty_cycle == current_dc - 0.9 * (current_dc - (0.1 * target_rpm + 20))


def test_stirring_will_try_to_restart_and_dodge_od_reading() -> None:
    # TODO make this an actual test
    from pioreactor.background_jobs.od_reading import start_od_reading

    exp = "test_stirring_will_try_to_restart_and_dodge_od_reading"
    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()
    with start_od_reading(
        "90", interval=5.0, unit=unit, experiment=exp, fake_data=True, use_calibration=False
    ):
        with Stirrer(500, unit, exp, rpm_calculator=rpm_calculator) as st:  # type: ignore
            st.start_stirring()

            pause(20)


def test_block_until_rpm_is_close_to_target_will_timeout() -> None:
    exp = "test_block_until_rpm_is_close_to_target_will_timeout"
    rpm_calculator = MockRpmCalculator()
    rpm_calculator.setup()
    with Stirrer(
        2 * MockRpmCalculator.ALWAYS_RETURN_RPM, unit, exp, rpm_calculator=rpm_calculator  # type: ignore
    ) as st:
        with catchtime() as delta:
            st.block_until_rpm_is_close_to_target(timeout=10)
        assert delta() < 12


def test_block_until_rpm_is_close_will_exit() -> None:
    exp = "test_block_until_rpm_is_close_to_target_will_timeout"
    rpm_calculator = MockRpmCalculator()
    rpm_calculator.setup()
    with Stirrer(
        MockRpmCalculator.ALWAYS_RETURN_RPM, unit, exp, rpm_calculator=rpm_calculator  # type: ignore
    ) as st:
        with catchtime() as delta:
            st.block_until_rpm_is_close_to_target(timeout=50)
        assert delta() < 7
