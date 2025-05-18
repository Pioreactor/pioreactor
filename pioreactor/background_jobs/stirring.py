# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import suppress
from threading import RLock
from time import perf_counter
from time import sleep
from time import time
from typing import Callable
from typing import cast
from typing import Optional

import click

import pioreactor.types as pt
from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import structs
from pioreactor.background_jobs.base import BackgroundJobWithDodging
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils import JobManager
from pioreactor.utils.pwm import PWM
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import paused_timer
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

if is_testing_env():
    from pioreactor.utils.mock import MockRpmCalculator
    from pioreactor.utils.mock import MockCallback
    from pioreactor.utils.mock import MockHandle


class RpmCalculator:
    """
    Super class for determining how to calculate the RPM from the hall sensor.

    Examples
    -----------

    > rpm_calc = RpmCalculator()
    > rpm_calc.setup()
    > rpm_estimate = rpm_calc.estimate(seconds_to_observe=1.5)

    """

    def __init__(self) -> None:
        pass

    def setup(self) -> None:
        import lgpio

        # we delay the setup so that when all other checks are done (like in stirring's uniqueness), we can start to
        # use the GPIO for this.

        if not is_testing_env():
            self._handle = lgpio.gpiochip_open(hardware.GPIOCHIP)
            lgpio.gpio_claim_input(self._handle, hardware.HALL_SENSOR_PIN, lgpio.SET_PULL_UP)

            lgpio.gpio_claim_alert(
                self._handle, hardware.HALL_SENSOR_PIN, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP
            )
            self._edge_callback = lgpio.callback(self._handle, hardware.HALL_SENSOR_PIN, lgpio.FALLING_EDGE)
        else:
            self._edge_callback = MockCallback()
            self._handle = MockHandle()

        self.turn_off_collection()

    def turn_off_collection(self) -> None:
        self.collecting = False
        self._edge_callback.cancel()

    def turn_on_collection(self) -> None:
        import lgpio

        self.collecting = True

        if not is_testing_env():
            self._edge_callback = lgpio.callback(
                self._handle, hardware.HALL_SENSOR_PIN, lgpio.FALLING_EDGE, self.callback
            )

    def clean_up(self) -> None:
        import lgpio

        with suppress(AttributeError):
            self._edge_callback.cancel()
            lgpio.gpiochip_close(self._handle)

    def estimate(self, seconds_to_observe: float) -> float:
        return 0.0

    def callback(self, *args) -> None:
        pass

    def sleep_for(self, seconds: float) -> None:
        sleep(seconds)

    def __enter__(self) -> RpmCalculator:
        return self

    def __exit__(self, *args) -> None:
        self.clean_up()


class RpmFromFrequency(RpmCalculator):
    """
    Averages the duration between pings (edges) in an N second window.

    Can't reliably compute faster than 2000 rpm on an RPi.
    """

    _running_sum = 0.0
    _running_min = 100
    _running_max = -100
    _running_count = 0
    _start_time = None

    def callback(self, *args) -> None:
        _start_time = self._start_time
        obs_time = perf_counter()
        if not self.collecting:
            return

        if _start_time is not None:
            delta = obs_time - _start_time
            self._running_sum += delta
            self._running_count += 1
            self._running_min = min(self._running_min, delta)
            self._running_max = max(self._running_max, delta)

        self._start_time = obs_time

    def clear_aggregates(self) -> None:
        self._running_sum = 0.0
        self._running_count = 0
        self._start_time = None
        self._running_min = 100
        self._running_max = -100

    def estimate(self, seconds_to_observe: float) -> float:
        self.clear_aggregates()
        self.turn_on_collection()
        self.sleep_for(seconds_to_observe)
        self.turn_off_collection()

        # self._running_max  / self._running_min # in a high vortex, noisy case, these aren't more than 25% apart.
        # at 3200 RPM, we still aren't seeing much difference here. I'm pretty confident we don't see skipping.

        if self._running_sum == 0.0:
            return 0.0
        else:
            return round(self._running_count * 60 / self._running_sum, 1)


class Stirrer(BackgroundJobWithDodging):
    """
    Parameters
    ------------

    target_rpm: float
        Send message to "pioreactor/{unit}/{experiment}/stirring/target_rpm/set" to change the stirring speed.
    rpm_calculator: RpmCalculator
        See RpmCalculator and examples below.
    hertz: float
        The PWM's frequency, measured in hz

    Notes
    -------

    To create a feedback loop between the duty-cycle level and the RPM, we set up a polling algorithm. We set up
    an edge detector on the hall sensor pin, and count the number of pulses in N seconds. We convert this count to RPM, and
    then use a PID system to update the amount of duty cycle to apply.

    We perform the above every N seconds. That is, there is PID controller that checks every N seconds and nudges the duty cycle
    to match the requested RPM.


    Examples
    ---------

    > st = Stirrer(500, unit, experiment)
    > st.start_stirring()
    """

    job_name = "stirring"
    published_settings = {
        "target_rpm": {"datatype": "float", "settable": True, "unit": "RPM"},
        "measured_rpm": {"datatype": "MeasuredRPM", "settable": False, "unit": "RPM"},
        "duty_cycle": {"datatype": "float", "settable": True, "unit": "%"},
    }
    # the _estimate_duty_cycle parameter is like the unrealized DC, and the duty_cycle is the realized DC.
    _estimate_duty_cycle: float = config.getfloat("stirring.config", "initial_duty_cycle", fallback=30)
    duty_cycle: float = 0
    _measured_rpm: Optional[float] = None

    def __init__(
        self,
        target_rpm: Optional[float],
        unit: str,
        experiment: str,
        rpm_calculator: Optional[RpmCalculator] = None,
        calibration: bool | structs.SimpleStirringCalibration | None = True,
    ) -> None:
        super(Stirrer, self).__init__(unit=unit, experiment=experiment)
        self.rpm_calculator = rpm_calculator

        if not hardware.is_HAT_present():
            self.logger.error("Pioreactor HAT must be present.")
            self.clean_up()
            raise exc.HardwareNotFoundError("Pioreactor HAT must be present.")

        if (self.rpm_calculator is not None) and not hardware.is_heating_pcb_present():
            self.logger.error("Heating PCB must be present to measure RPM.")
            self.clean_up()
            raise exc.HardwareNotFoundError("Heating PCB must be present to measure RPM.")

        if self.rpm_calculator is not None:
            self.logger.debug("Operating with RPM feedback loop.")
        else:
            self.logger.debug("Operating without RPM feedback loop.")

        channel: Optional[pt.PwmChannel] = cast(pt.PwmChannel, config.get("PWM_reverse", "stirring"))

        if channel is None:
            self.logger.error("Add stirring to [PWM] section to configuration file.")
            self.clean_up()
            return

        pin: pt.GpioPin = hardware.PWM_TO_PIN[channel]
        self.pwm = PWM(
            pin,
            config.getfloat("stirring.config", "pwm_hz"),
            unit=self.unit,
            experiment=self.experiment,
            pub_client=self.pub_client,
            logger=self.logger,
        )
        self.pwm.start(0)
        self.pwm.lock()
        self.duty_cycle_lock = RLock()

        if target_rpm is not None and self.rpm_calculator is not None:
            self.target_rpm: Optional[float] = float(target_rpm)
        else:
            self.target_rpm = None

        # initialize DC with initial_duty_cycle, however we can update it with a lookup (if it exists)
        self.rpm_to_dc_lookup = self.initialize_rpm_to_dc_lookup(calibration)
        self._estimate_duty_cycle = self.rpm_to_dc_lookup(self.target_rpm)

        # set up PID
        self.pid = PID(
            Kp=config.getfloat("stirring.pid", "Kp"),
            Ki=config.getfloat("stirring.pid", "Ki"),
            Kd=config.getfloat("stirring.pid", "Kd"),
            setpoint=self.target_rpm or 0,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="rpm",
            output_limits=(-7.5, 7.5),  # avoid whiplashing
            pub_client=self.pub_client,
        )

    def action_to_do_before_od_reading(self):
        self.stop_stirring()

    def action_to_do_after_od_reading(self):
        self.start_stirring()
        sleep(1)
        self.poll_and_update_dc()

    def initialize_dodging_operation(self):
        if config.getfloat("od_reading.config", "samples_per_second") > 0.12:
            self.logger.warning(
                "Recommended to decrease `samples_per_second` to ensure there is time to start/stop stirring. Try 0.12 or less."
            )

        with suppress(AttributeError):
            self.rpm_check_repeated_timer.cancel()

        self.rpm_check_repeated_timer = RepeatedTimer(
            1_000,
            lambda *args: None,
            job_name=self.job_name,
            logger=self.logger,
        )
        with self.duty_cycle_lock:
            self.stop_stirring()  # we'll start it again in action_to_do_after_od_reading

    def initialize_continuous_operation(self):
        # set up thread to periodically check the rpm
        self.rpm_check_repeated_timer = RepeatedTimer(
            config.getfloat("stirring.config", "duration_between_updates_seconds", fallback=23.0),
            self.poll_and_update_dc,
            job_name=self.job_name,
            run_immediately=True,
            run_after=6,
            logger=self.logger,
        ).start()

        if self.duty_cycle == 0:
            self.start_stirring()

    def initialize_rpm_to_dc_lookup(
        self, calibration: bool | structs.SimpleStirringCalibration | None
    ) -> Callable:
        if self.rpm_calculator is None:
            # if we can't track RPM, no point in adjusting DC, use current value
            assert self.target_rpm is None
            return lambda rpm: self._estimate_duty_cycle

        assert isinstance(self.target_rpm, float)

        if calibration is True:
            possible_calibration = load_active_calibration("stirring")
        elif isinstance(calibration, structs.CalibrationBase):
            possible_calibration = calibration
        else:
            possible_calibration = None

        if possible_calibration is not None:
            cal = possible_calibration

            if cal.y != "RPM":
                self.logger.error(f"Calibration {cal.calibration_name} has wrong type.")
                raise exc.CalibrationError(f"Calibration {cal.calibration_name} has wrong type.")

            self.logger.debug(f"Found stirring calibration: {cal.calibration_name}.")

            # since we have calibration data, and the initial_duty_cycle could be
            # far off, giving the below equation a bad "first step". We set it here.
            self._estimate_duty_cycle = cal.y_to_x(self.target_rpm)

            # we scale this by 90% to make sure the PID + prediction doesn't overshoot,
            # better to be conservative here.
            # equivalent to a weighted average: 0.1 * current + 0.9 * predicted
            return lambda rpm: self._estimate_duty_cycle - 0.90 * (
                self._estimate_duty_cycle - (cal.y_to_x(rpm))
            )
        else:
            return lambda rpm: self._estimate_duty_cycle

    def on_disconnected(self) -> None:
        super().on_disconnected()
        with suppress(AttributeError):
            self.rpm_check_repeated_timer.cancel()
        with suppress(AttributeError):
            self.pwm.clean_up()
        with suppress(AttributeError):
            self.pid.clean_up()
        with suppress(AttributeError):
            if self.rpm_calculator:
                self.rpm_calculator.clean_up()

    def start_stirring(self) -> None:
        self.set_duty_cycle(100)  # get momentum to start
        sleep(0.35)
        self.set_duty_cycle(self._estimate_duty_cycle)
        self.rpm_check_repeated_timer.unpause()

    def stop_stirring(self) -> None:
        self.set_duty_cycle(0)  # get momentum to start
        self.rpm_check_repeated_timer.pause()
        if self.rpm_calculator is not None:
            self.measured_rpm = structs.MeasuredRPM(timestamp=current_utc_datetime(), measured_rpm=0)

    def kick_stirring(self) -> None:
        self.logger.debug("Kicking stirring")
        self.set_duty_cycle(0)
        sleep(0.75)
        self.set_duty_cycle(100)
        sleep(0.5)
        self.set_duty_cycle(
            min(1.01 * self._estimate_duty_cycle, 60)
        )  # DC should never need to be above 60 - simply not realistic. We want to avoid the death spiral to 100%.

    def kick_stirring_but_avoid_od_reading(self) -> None:
        """
        This will determine when the next od reading occurs (if possible), and
        wait until it completes before kicking stirring or sneak in early.
        """
        with JobManager() as jm:
            interval = float(jm.get_setting_from_running_job("od_reading", "interval", timeout=5))
            first_od_obs_time = float(
                jm.get_setting_from_running_job("od_reading", "first_od_obs_time", timeout=5)
            )

        seconds_to_next_reading = interval - (time() - first_od_obs_time) % interval

        # if seconds_to_next_reading is like 50s (high duration between ODs), let's kick now and not wait.
        if seconds_to_next_reading <= 2:
            sleep(
                seconds_to_next_reading + 2
            )  # add an additional 2 seconds to make sure we wait long enough for OD reading to complete.

        self.kick_stirring()
        return

    def poll(self, poll_for_seconds: float) -> Optional[float]:
        """
        Returns an MeasuredRPM, or None if not measuring RPM.
        """
        if self.rpm_calculator is None:
            return None

        recent_rpm = self.rpm_calculator.estimate(poll_for_seconds)

        self._measured_rpm = recent_rpm
        self.measured_rpm = structs.MeasuredRPM(
            timestamp=current_utc_datetime(), measured_rpm=self._measured_rpm
        )

        if recent_rpm == 0 and self.state == self.READY:  # and not is_testing_env():
            self.logger.warning(
                "Stirring RPM is 0 - attempting to restart it automatically. It may be a temporary stall, target RPM may be too low, insufficient power applied to fan, or not reading sensor correctly."
            )
            self.blink_error_code(error_codes.STIRRING_FAILED)

            is_od_running = is_pio_job_running("od_reading")
            is_dodging = self.currently_dodging_od

            if not is_od_running or is_dodging:
                # if dodging, poll only runs when needed (outside od readings), so it's always safe to kick.
                self.kick_stirring()
            else:
                self.kick_stirring_but_avoid_od_reading()

        return self._measured_rpm

    def update_dc_with_measured_rpm(self, measured_rpm: Optional[float]) -> None:
        if measured_rpm is None or self.state != self.READY:
            return
        self._estimate_duty_cycle += self.pid.update(measured_rpm)
        self.set_duty_cycle(self._estimate_duty_cycle)

    def poll_and_update_dc(self, poll_for_seconds: Optional[float] = None) -> None:
        if self.rpm_calculator is None or self.target_rpm is None or self.state != self.READY:
            return

        if poll_for_seconds is None:
            target_n_data_points = 12
            rps = self.target_rpm / 60.0
            poll_for_seconds = max(
                1, min(target_n_data_points / rps, 5)
            )  # things can break if this function takes too long, but always get _some_ data.

        measured_rpm = self.poll(poll_for_seconds)
        self.update_dc_with_measured_rpm(measured_rpm)
        return

    def on_ready_to_sleeping(self) -> None:
        self.stop_stirring()

    def on_sleeping_to_ready(self) -> None:
        super().on_sleeping_to_ready()
        self.duty_cycle = self._estimate_duty_cycle
        self.rpm_check_repeated_timer.unpause()
        self.start_stirring()

    def set_duty_cycle(self, value: float) -> None:
        with self.duty_cycle_lock:
            self.duty_cycle = clamp(0.0, round(value, 5), 100.0)
            self.pwm.change_duty_cycle(self.duty_cycle)

    def set_target_rpm(self, value: float) -> None:
        if self.rpm_calculator is None:
            # probably use_rpm=0 is in config.ini
            raise ValueError("Can't set target RPM when no RPM measurement is being made")

        self.target_rpm = clamp(0.0, float(value), 5_000.0)

        if self.target_rpm == 0:
            self._estimate_duty_cycle = 0
        else:
            self._estimate_duty_cycle = self.rpm_to_dc_lookup(self.target_rpm)

        self.set_duty_cycle(self._estimate_duty_cycle)
        self.pid.set_setpoint(self.target_rpm)

    def sleep_if_ready(self, seconds):
        if self.state == self.READY:
            sleep(seconds)

    def block_until_rpm_is_close_to_target(
        self, abs_tolerance: float = 20, timeout: Optional[float] = 60
    ) -> bool:
        """
        This function blocks until the stirring is "close enough" to the target RPM.

        Parameters
        -----------
        abs_tolerance:
            The maximum delta between current RPM and the target RPM.
        timeout:
            When timeout is not None, block at this function for maximum timeout seconds.

        Returns
        --------
        bool: True if successfully waited until RPM is correct.
        """
        if (
            self.rpm_calculator is None or self.target_rpm is None or self.currently_dodging_od
        ):  # or is_testing_env():
            # Can't block if we aren't recording the RPM
            return False

        def should_exit() -> bool:
            """Encapsulates exit conditions to simplify the main loop."""
            return self.state != self.READY or self.currently_dodging_od

        with paused_timer(self.rpm_check_repeated_timer):  # Automatically pause/unpause
            assert isinstance(self.target_rpm, float)
            sleep_time = 0.2
            poll_time = 1.5
            self.logger.debug(f"{self.job_name} is blocking until RPM is near {self.target_rpm}.")

            with catchtime() as time_waiting:
                if should_exit():
                    return False
                sleep(2)  # On init, the stirring is too fast from the initial "kick"

                with self.duty_cycle_lock:
                    if should_exit():
                        return False
                    self.poll_and_update_dc(poll_time)

                assert self._measured_rpm is not None

                while abs(self._measured_rpm - self.target_rpm) > abs_tolerance:
                    if should_exit():
                        return False
                    sleep(sleep_time)

                    with self.duty_cycle_lock:
                        if should_exit():
                            return False
                        self.poll_and_update_dc(poll_time)

                    if timeout and time_waiting() > timeout:
                        self.logger.debug(
                            f"Waited {time_waiting():.1f} seconds for RPM to match, breaking out early."
                        )
                        return False

        return True


def start_stirring(
    target_rpm: Optional[float] = config.getfloat("stirring.config", "target_rpm", fallback=400),
    unit: Optional[str] = None,
    experiment: Optional[str] = None,
    use_rpm: bool = config.getboolean("stirring.config", "use_rpm", fallback="true"),
    calibration: bool | structs.SimpleStirringCalibration | None = True,
) -> Stirrer:
    unit = unit or get_unit_name()
    experiment = experiment or get_assigned_experiment_name(unit)

    if use_rpm and not is_testing_env():
        rpm_calculator = RpmFromFrequency()
        rpm_calculator.setup()
    elif use_rpm and is_testing_env():
        rpm_calculator = MockRpmCalculator()  # type: ignore
        rpm_calculator.setup()
    else:
        rpm_calculator = None

    stirrer = Stirrer(
        target_rpm=target_rpm,
        unit=unit,
        experiment=experiment,
        rpm_calculator=rpm_calculator,
        calibration=calibration,
    )
    return stirrer


@click.command(name="stirring")
@click.option(
    "--target-rpm",
    default=config.getfloat("stirring.config", "target_rpm", fallback=400),
    help="set the target RPM",
    show_default=True,
    type=click.FloatRange(0, 1500, clamp=True),
)
@click.option(
    "--use-rpm/--ignore-rpm", default=config.getboolean("stirring.config", "use_rpm", fallback="true")
)
def click_stirring(target_rpm: float, use_rpm: bool) -> None:
    """
    Start the stirring of the Pioreactor.
    """
    with start_stirring(target_rpm=target_rpm, use_rpm=use_rpm) as st:
        st.block_until_rpm_is_close_to_target()
        st.block_until_disconnected()
