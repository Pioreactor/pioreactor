# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import time

import pioreactor.background_jobs.stirring as stirring_mod
import pytest
from click.testing import CliRunner
from pioreactor.background_jobs.od_reading import start_od_reading
from pioreactor.background_jobs.stirring import start_stirring
from pioreactor.background_jobs.stirring import Stirrer
from pioreactor.pubsub import publish
from pioreactor.pubsub import subscribe
from pioreactor.pubsub import subscribe_and_callback
from pioreactor.structs import SimpleStirringCalibration
from pioreactor.utils.mock import MockRpmCalculator as RpmCalculator
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
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
        st.stop_stirring()
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
    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()
    with Stirrer(target_rpm, unit, exp, rpm_calculator=rpm_calculator) as st:
        st.start_stirring()
        assert st.target_rpm == target_rpm

        pause(22)

        message = subscribe(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", timeout=3)
        assert message is not None
        assert json.loads(message.payload)["measured_rpm"] == 500


def test_rpm_isnt_updated_if_there_is_no_rpm_measurement() -> None:
    exp = "test_rpm_isnt_updated_if_there_is_no_rpm_measurement"

    publish(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", None, retain=True)
    pause()

    target_rpm = 500

    with Stirrer(target_rpm, unit, exp, rpm_calculator=None) as st:
        st.start_stirring()
        assert st.target_rpm is None

        pause(22)

        message = subscribe(f"pioreactor/{unit}/{exp}/stirring/measured_rpm", timeout=1)
        assert message is None


def test_stirring_with_calibration() -> None:
    exp = "test_stirring_with_calibration"

    class FakeRpmCalculator:
        def setup(self):
            return

        def __call__(self, *args):
            return 475

        def clean_up(self):
            pass

    linear_term, constant_term = 10, -5
    cal = SimpleStirringCalibration(
        calibration_name="test_stirring_with_calibration",
        calibrated_on_pioreactor_unit=unit,
        created_at=current_utc_datetime(),
        curve_data_=[linear_term, constant_term],
        curve_type="poly",
        pwm_hz=200,
        voltage=5.0,
        recorded_data={"x": [], "y": []},
    )

    target_rpm = 500
    rpm_calculator = FakeRpmCalculator()
    rpm_calculator.setup()
    with Stirrer(target_rpm, unit, exp, rpm_calculator=rpm_calculator, calibration=cal) as st:  # type: ignore
        st.start_stirring()

        initial_dc = st.duty_cycle
        target_rpm = 600
        st.set_target_rpm(target_rpm)
        pause()

        assert st.duty_cycle > initial_dc

        assert st.rpm_to_dc_lookup(600) == 63.760213125
        assert st.rpm_to_dc_lookup(700) == 73.21021312500001


def test_stirring_wont_fire_last_100dc_on_od_reading_end() -> None:
    # regression test for BackgroundJobWithDodging, but first observed in stirring job

    exp = "test_stirring_wont_fire_last_100dc_on_od_reading_end"

    bucket = []

    def collect(msg):
        pl = json.loads(msg.payload.decode())
        if pl:
            bucket.append(pl)

    with start_stirring(
        target_rpm=500,
        unit=unit,
        experiment=exp,
        use_rpm=True,
        enable_dodging_od=True,
        target_rpm_during_od_reading=100,
        target_rpm_outside_od_reading=300,
    ) as st:
        with start_od_reading(
            "90", None, interval=10.0, unit=unit, experiment=exp, fake_data=True, calibration=False
        ):
            assert st._estimate_duty_cycle > 0
            assert st.currently_dodging_od
            assert st.enable_dodging_od
            time.sleep(15)
            subscribe_and_callback(collect, f"pioreactor/{unit}/{exp}/pwms/dc", allow_retained=False)

        time.sleep(2)
    time.sleep(1)
    assert bucket == []


def test_stirring_will_try_to_restart_and_dodge_od_reading() -> None:
    exp = "test_stirring_will_try_to_restart_and_dodge_od_reading"

    with start_od_reading("90", None, interval=10.0, unit=unit, experiment=exp, fake_data=True):
        with start_stirring(500, unit, exp, use_rpm=True, enable_dodging_od=True) as st:
            assert st.duty_cycle == 0
            assert st._estimate_duty_cycle > 0
            assert st.currently_dodging_od
            assert st.enable_dodging_od


def test_target_rpm_during_od_reading_defaults_to_zero() -> None:
    exp = "test_target_rpm_during_od_reading_defaults_to_zero"

    with start_od_reading("90", None, interval=10.0, unit=unit, experiment=exp, fake_data=True):
        with start_stirring(500, unit, exp, use_rpm=True, enable_dodging_od=True) as st:
            # default target_rpm_during_od_reading should be 0.0 and no error occurs
            assert st.target_rpm_during_od_reading == 0.0
            # default target_rpm_outside_od_reading should fall back to target_rpm
            assert st.target_rpm_outside_od_reading == 500


def test_block_until_rpm_is_close_to_target_will_timeout() -> None:
    exp = "test_block_until_rpm_is_close_to_target_will_timeout"
    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()
    with Stirrer(
        2 * RpmCalculator.ALWAYS_RETURN_RPM, unit, exp, rpm_calculator=rpm_calculator  # type: ignore
    ) as st:
        with catchtime() as delta:
            st.block_until_rpm_is_close_to_target(timeout=10)
        assert delta() < 12


def test_block_until_rpm_is_close_will_exit() -> None:
    exp = "test_block_until_rpm_is_close_will_exit"
    rpm_calculator = RpmCalculator()
    rpm_calculator.setup()
    with Stirrer(
        RpmCalculator.ALWAYS_RETURN_RPM, unit, exp, rpm_calculator=rpm_calculator  # type: ignore
    ) as st:
        with catchtime() as delta:
            st.block_until_rpm_is_close_to_target(timeout=50)
        assert delta() < 7


class DummyStirrer:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def block_until_rpm_is_close_to_target(self):
        pass

    def block_until_disconnected(self):
        pass


@pytest.fixture(autouse=True)
def dummy_start_stirring(monkeypatch):
    """Replace start_stirring to capture its kwargs and return a dummy context manager."""
    calls = {}

    def fake_start_stirring(**kwargs):
        calls.update(kwargs)
        return DummyStirrer()

    monkeypatch.setattr(stirring_mod, "start_stirring", fake_start_stirring)
    return calls


def test_click_stirring_accepts_new_flags(dummy_start_stirring):
    runner = CliRunner()
    result = runner.invoke(
        stirring_mod.click_stirring,
        [
            "--target-rpm",
            "250",
            "--use-rpm",
            "true",
            "--duty-cycle",
            "42.5",
            "--target-rpm-during-od-reading",
            "123.0",
            "--target-rpm-outside-od-reading",
            "456.0",
        ],
    )
    assert result.exit_code == 0, result.output
    # Ensure start_stirring was called with the flag values
    assert dummy_start_stirring["target_rpm"] == 250.0
    assert dummy_start_stirring["use_rpm"] is True
    assert dummy_start_stirring["duty_cycle"] == 42.5
    assert dummy_start_stirring["target_rpm_during_od_reading"] == 123.0
    assert dummy_start_stirring["target_rpm_outside_od_reading"] == 456.0


@pytest.mark.parametrize(
    "flag",
    [
        "--duty-cycle",
        "--target-rpm-during-od-reading",
        "--target-rpm-outside-od-reading",
    ],
)
def test_click_stirring_help_includes_new_flags(flag):
    runner = CliRunner()
    result = runner.invoke(stirring_mod.click_stirring, ["--help"])
    assert result.exit_code == 0
    assert flag in result.output
