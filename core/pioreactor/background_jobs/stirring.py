# -*- coding: utf-8 -*-
from __future__ import annotations

from contextlib import suppress
from threading import RLock
from time import sleep
from time import time
from typing import cast
from typing import override

import click
import pioreactor.types as pt
from pioreactor import error_codes
from pioreactor import exc
from pioreactor import hardware
from pioreactor import structs
from pioreactor.background_jobs.base import BackgroundJobWithDodging
from pioreactor.calibrations import load_active_calibration
from pioreactor.config import config
from pioreactor.states import JobState as st
from pioreactor.utils import clamp
from pioreactor.utils import is_pio_job_running
from pioreactor.utils.job_manager import JobManager
from pioreactor.utils.pwm import PWM
from pioreactor.utils.streaming_calculations import PID
from pioreactor.utils.timing import catchtime
from pioreactor.utils.timing import current_utc_datetime
from pioreactor.utils.timing import paused_timer
from pioreactor.utils.timing import RepeatedTimer
from pioreactor.whoami import get_assigned_experiment_name
from pioreactor.whoami import get_unit_name
from pioreactor.whoami import is_testing_env

# the RPM sensor can't reliably measure faster than this. See RpmFromFrequency.
MAX_TARGET_RPM = 2_000.0
# seconds of 100% duty cycle to get a stopped stir bar moving.
START_KICK_SECONDS = 0.5
# longer, to recover a stalled (decoupled) stir bar.
STALL_KICK_SECONDS = 0.75

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

        hall_sensor_pin = hardware.get_hall_sensor_pin()
        self._hall_sensor_pin = hall_sensor_pin

        if not is_testing_env():
            self._handle = lgpio.gpiochip_open(hardware.determine_gpiochip())
            lgpio.gpio_claim_input(self._handle, hall_sensor_pin, lgpio.SET_PULL_UP)

            lgpio.gpio_claim_alert(self._handle, hall_sensor_pin, lgpio.FALLING_EDGE, lgpio.SET_PULL_UP)
            self._edge_callback = lgpio.callback(self._handle, hall_sensor_pin, lgpio.FALLING_EDGE)
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
                self._handle, self._hall_sensor_pin, lgpio.FALLING_EDGE, self.callback
            )

    def clean_up(self) -> None:
        import lgpio

        with suppress(AttributeError):
            self._edge_callback.cancel()
            lgpio.gpiochip_close(self._handle)

    def estimate(self, seconds_to_observe: float) -> float:
        return 0.0

    def callback(self, _chip: int, _gpio: int, _level: int, _timestamp_ns: int) -> None:
        pass

    def sleep_for(self, seconds: float) -> None:
        sleep(seconds)

    def __enter__(self) -> "RpmCalculator":
        return self

    def __exit__(self, *args: object) -> None:
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

    def callback(self, _chip: int, _gpio: int, _level: int, timestamp_ns: int) -> None:
        _start_time = self._start_time
        obs_time = timestamp_ns / 1_000_000_000
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
    # None while dodging: the RPM is only polled after each OD reading.
    rpm_check_repeated_timer: RepeatedTimer | None = None
    # the _estimate_duty_cycle parameter is like the unrealized DC, and the duty_cycle is the realized DC.
    # It is the duty cycle learned for target_rpm. Pausing for OD readings never changes it.
    _estimate_duty_cycle: float
    duty_cycle: float = 0
    _measured_rpm: float | None = None
    calibration: structs.SimpleStirringCalibration | None = None
    target_rpm_during_od_reading: float | None = None
    # True from action_to_do_before_od_reading until the fan is restored after the reading.
    # Guarded by duty_cycle_lock.
    _paused_for_od_reading: bool = False

    def __init__(
        self,
        target_rpm: float | None,
        unit: pt.Unit,
        experiment: pt.Experiment,
        rpm_calculator: RpmCalculator | MockRpmCalculator | None = None,
        calibration: bool | structs.SimpleStirringCalibration | None = True,
        enable_dodging_od: bool = False,
        duty_cycle: float | None = None,
        target_rpm_during_od_reading: float | None = None,
    ) -> None:
        super(Stirrer, self).__init__(unit=unit, experiment=experiment, enable_dodging_od=enable_dodging_od)
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

        channel: pt.PwmChannel | None = cast(pt.PwmChannel, config.get("PWM_reverse", "stirring"))

        if channel is None:
            self.logger.error("Add stirring to [PWM] section to configuration file.")
            self.clean_up()
            return

        pin: pt.GpioPin = hardware.get_pwm_to_pin_map()[channel]
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
            self.target_rpm: float | None = float(target_rpm)
        else:
            self.target_rpm = None

        # initialize DC with initial_duty_cycle, however we can update it with a lookup (if it exists)
        if duty_cycle is None:
            self._estimate_duty_cycle = config.getfloat("stirring.config", "initial_duty_cycle", fallback=30)
        else:
            self._estimate_duty_cycle = duty_cycle

        if self.target_rpm is not None:
            self.calibration = self.load_calibration(calibration)
            predicted_duty_cycle = self.predict_duty_cycle(self.target_rpm)
            if predicted_duty_cycle is not None:
                # the initial_duty_cycle could be far off, giving a bad "first step", so start from the prediction.
                self._estimate_duty_cycle = predicted_duty_cycle
            self._estimate_duty_cycle = self.duty_cycle_estimate_for(self.target_rpm)

            if self.calibration is None and self.enable_dodging_od:
                self.logger.warning(
                    "OD dodging is enabled without a stirring calibration. "
                    "This can increase OD reading noise. Run a stirring calibration for better stability."
                )

        if target_rpm_during_od_reading is not None:
            self.target_rpm_during_od_reading = target_rpm_during_od_reading
        else:
            self.target_rpm_during_od_reading = config.getfloat(
                "stirring.config", "target_rpm_during_od_reading", fallback=0.0
            )

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

    @override
    def action_to_do_before_od_reading(self) -> None:
        # pausing for an OD reading never changes target_rpm, _estimate_duty_cycle, or the PID.
        with self.duty_cycle_lock:
            # dodging may have been turned off between the timer's check and now.
            if not self.currently_dodging_od:
                return
            self._paused_for_od_reading = True
            self.set_duty_cycle(self.duty_cycle_during_od_reading())

    @override
    def action_to_do_after_od_reading(self) -> None:
        with self.duty_cycle_lock:
            self._paused_for_od_reading = False
            self.apply_duty_cycle(self._estimate_duty_cycle)
            sleep(0.15)
            self.poll_and_update_dc()  # do it twice.
            self.poll_and_update_dc()

    def duty_cycle_during_od_reading(self) -> float:
        assert self.target_rpm_during_od_reading is not None
        during_rpm = self.target_rpm_during_od_reading
        if during_rpm == 0:
            return 0.0

        predicted_duty_cycle = self.predict_duty_cycle(during_rpm)
        if predicted_duty_cycle is not None:
            return predicted_duty_cycle

        # without a calibration, assume duty cycle scales linearly with RPM from what we've learned for target_rpm.
        if self.target_rpm:
            return clamp(0.0, self._estimate_duty_cycle * during_rpm / self.target_rpm, 100.0)
        return self._estimate_duty_cycle

    @override
    def initialize_dodging_operation(self) -> None:
        self.logger.debug("Starting initialize_dodging_operation")
        with JobManager() as jm:
            interval = float(jm.get_setting_from_running_job("od_reading", "interval", timeout=5))

        if (interval or 0.0) < 1 / 0.12:
            self.logger.warning(
                "Recommended to increase `seconds_between_readings` to ensure there is time to start/stop stirring. Try 8 or more."
            )

        # while dodging, the RPM is polled in action_to_do_after_od_reading instead.
        if self.rpm_check_repeated_timer is not None:
            self.rpm_check_repeated_timer.cancel()
            self.rpm_check_repeated_timer = None

        with self.duty_cycle_lock:
            self.stop_stirring()  # we'll start it again in action_to_do_after_od_reading

        # publish the target_rpm_during_od_reading:
        self.add_to_published_settings(
            "target_rpm_during_od_reading", {"datatype": "float", "settable": True, "unit": "RPM"}
        )
        self.logger.debug("Finished initialize_dodging_operation")

    @override
    def initialize_continuous_operation(self) -> None:
        self.logger.debug("Starting initialize_continuous_operation")
        if self.rpm_calculator is not None and self.target_rpm is None:
            repeated_action = self.poll
            repeated_action_args: tuple[object, ...] = (4.0,)
        else:
            repeated_action = self.poll_and_update_dc
            repeated_action_args = ()

        if self.rpm_check_repeated_timer is not None:
            self.rpm_check_repeated_timer.cancel()

        # set up thread to periodically check the rpm
        self.rpm_check_repeated_timer = RepeatedTimer(
            config.getfloat("stirring.config", "duration_between_updates_seconds", fallback=23.0),
            repeated_action,
            job_name=self.job_name,
            run_immediately=True,
            run_after=6,
            logger=self.logger,
            args=repeated_action_args,
        ).start()

        with self.duty_cycle_lock:
            # we may have been paused for an OD reading. target_rpm was never changed, so just start again.
            was_paused_for_od_reading = self._paused_for_od_reading
            self._paused_for_od_reading = False
            if self.duty_cycle == 0:
                self.start_stirring()
            elif was_paused_for_od_reading:
                # still at the (non-zero) duty cycle for target_rpm_during_od_reading.
                self.set_duty_cycle(self._estimate_duty_cycle)

        self.remove_from_published_settings("target_rpm_during_od_reading")
        self.logger.debug("Finished initialize_continuous_operation")

    def load_calibration(
        self, calibration: bool | structs.SimpleStirringCalibration | None
    ) -> structs.SimpleStirringCalibration | None:
        if calibration is True:
            possible_calibration = load_active_calibration("stirring")
        elif isinstance(calibration, structs.CalibrationBase):
            possible_calibration = calibration
        else:
            possible_calibration = None

        if possible_calibration is None:
            return None

        if possible_calibration.y != "RPM":
            self.logger.error(
                f"stirring calibration `{possible_calibration.calibration_name}` has wrong type."
            )
            raise exc.CalibrationError(
                f"stirring calibration `{possible_calibration.calibration_name}` has wrong type."
            )

        self.logger.debug(f"Found active stirring calibration `{possible_calibration.calibration_name}`.")
        return possible_calibration

    def predict_duty_cycle(self, rpm: float) -> float | None:
        """The calibration's duty cycle for `rpm`, or None without a calibration."""
        if self.calibration is None:
            return None
        return self.calibration.y_to_x(rpm)

    def duty_cycle_estimate_for(self, rpm: float) -> float:
        """
        Starting duty cycle for a new target `rpm`. Without a calibration, keep the learned estimate.
        With one, take a conservative step 90% of the way from the learned estimate towards the prediction
        (better not to overshoot), and aim 5% high so we're less likely to stall the fan. We'll converge later via updates.
        """
        predicted_duty_cycle = self.predict_duty_cycle(rpm)
        if predicted_duty_cycle is None:
            return self._estimate_duty_cycle
        return 1.05 * (self._estimate_duty_cycle - 0.90 * (self._estimate_duty_cycle - predicted_duty_cycle))

    def on_disconnected(self) -> None:
        super().on_disconnected()
        if self.rpm_check_repeated_timer is not None:
            self.rpm_check_repeated_timer.cancel()
        with suppress(AttributeError):
            self.pwm.clean_up()
        with suppress(AttributeError):
            self.pid.clean_up()
        with suppress(AttributeError):
            if self.rpm_calculator:
                self.rpm_calculator.clean_up()

    def spin_up(self, duty_cycle: float, kick_seconds: float) -> None:
        """Briefly apply 100% to get the stir bar moving, then settle at `duty_cycle`."""
        self.set_duty_cycle(100)
        if not is_testing_env():
            sleep(kick_seconds)
        self.set_duty_cycle(duty_cycle)

    def apply_duty_cycle(self, duty_cycle: float) -> None:
        """Change to `duty_cycle`, kicking first if the fan is currently stopped."""
        if self.duty_cycle == 0 and duty_cycle > 0:
            self.spin_up(duty_cycle, kick_seconds=START_KICK_SECONDS)
        else:
            self.set_duty_cycle(duty_cycle)

    def start_stirring(self) -> None:
        self.apply_duty_cycle(self._estimate_duty_cycle)
        if self.rpm_check_repeated_timer is not None:
            self.rpm_check_repeated_timer.unpause()

    def stop_stirring(self) -> None:
        self.set_duty_cycle(0)
        if self.rpm_check_repeated_timer is not None:
            self.rpm_check_repeated_timer.pause()
        if self.rpm_calculator is not None:
            self.measured_rpm = structs.MeasuredRPM(timestamp=current_utc_datetime(), measured_rpm=0)

    def kick_stirring(self) -> None:
        self.logger.debug("Kicking stirring")
        self.set_duty_cycle(0)
        sleep(STALL_KICK_SECONDS)
        # DC should never need to be above 60 - simply not realistic. We want to avoid the death spiral to 100%.
        self.spin_up(min(1.01 * self._estimate_duty_cycle, 60), kick_seconds=STALL_KICK_SECONDS)

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

    def poll(self, poll_for_seconds: float) -> float | None:
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

        target_rpm = self.target_rpm or 0
        if recent_rpm == 0 and self.state is st.READY and target_rpm > 0:  # and not is_testing_env():
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

    def update_dc_with_measured_rpm(self, measured_rpm: float | None) -> None:
        if measured_rpm is None or self.state is not st.READY:
            return
        self._estimate_duty_cycle = clamp(
            0.0, self._estimate_duty_cycle + self.pid.update(measured_rpm), 100.0
        )
        self.set_duty_cycle(self._estimate_duty_cycle)

    def poll_and_update_dc(self, poll_for_seconds: float | None = None) -> None:
        if self.rpm_calculator is None or self.target_rpm is None or self.state is not st.READY:
            return

        if poll_for_seconds is None:
            if self.target_rpm > 0:
                target_n_data_points = 10
                rps = self.target_rpm / 60.0
                poll_for_seconds = max(
                    1.0, min(target_n_data_points / rps, 5.0)
                )  # things can break if this function takes too long, but always get _some_ data.
            else:
                poll_for_seconds = 1.0

        measured_rpm = self.poll(poll_for_seconds)
        self.update_dc_with_measured_rpm(measured_rpm)
        return

    def on_ready_to_sleeping(self) -> None:
        with self.duty_cycle_lock:
            # if asleep mid OD reading, action_to_do_after_od_reading never runs for it.
            self._paused_for_od_reading = False
            self.stop_stirring()

    def on_sleeping_to_ready(self) -> None:
        super().on_sleeping_to_ready()
        if self.currently_dodging_od:
            # we might be inside an OD reading; the next action_to_do_after_od_reading starts the fan.
            return
        self.start_stirring()

    def set_duty_cycle(self, value: float) -> None:
        with self.duty_cycle_lock:
            if self.pwm.is_cleaned_up:
                self.logger.debug("Ignoring duty cycle update after PWM cleanup.")
                return

            self.duty_cycle = clamp(0.0, round(value, 5), 100.0)

            try:
                self.pwm.change_duty_cycle(self.duty_cycle)
            except ValueError:
                if self.pwm.is_cleaned_up:
                    self.logger.debug("Ignoring duty cycle update after PWM cleanup.")
                    return
                raise

    def set_target_rpm(self, value: float) -> None:
        if self.rpm_calculator is None:
            # probably use_rpm=0 is in config.ini
            raise ValueError("Can't set target RPM when no RPM measurement is being made")

        with self.duty_cycle_lock:
            self.update_target_rpm(value)

            # if paused, don't apply a kick or change live duty cycle.
            # if paused for an OD reading, action_to_do_after_od_reading will apply it.
            if self.state is st.SLEEPING or self._paused_for_od_reading:
                return

            self.apply_duty_cycle(self._estimate_duty_cycle)

    def update_target_rpm(self, value: float) -> None:
        """Change target_rpm, the PID setpoint, and the duty cycle estimate, without touching the fan."""
        self.target_rpm = clamp(0.0, float(value), MAX_TARGET_RPM)
        self.pid.set_setpoint(self.target_rpm)

        if self.target_rpm == 0:
            self._estimate_duty_cycle = 0
        else:
            self._estimate_duty_cycle = clamp(0.0, self.duty_cycle_estimate_for(self.target_rpm), 100.0)

    def block_until_rpm_is_close_to_target(
        self, abs_tolerance: float = 20, timeout: float | None = 60
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
            self.rpm_calculator is None
            or self.target_rpm is None
            or self.currently_dodging_od
            or self.rpm_check_repeated_timer is None
        ):  # or is_testing_env():
            # Can't block if we aren't recording the RPM
            return False

        def should_exit() -> bool:
            """Encapsulates exit conditions to simplify the main loop."""
            return self.state is not st.READY or self.currently_dodging_od

        with paused_timer(self.rpm_check_repeated_timer):  # Automatically pause/unpause
            assert isinstance(self.target_rpm, float)
            sleep_time = 0.2
            poll_time = 1.5
            self.logger.debug(f"{self.job_name} is blocking until RPM is near {self.target_rpm}.")

            with catchtime() as time_waiting:
                if should_exit():
                    return False
                if not is_testing_env():
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
    target_rpm: float | None = 500,
    unit: pt.Unit | None = None,
    experiment: pt.Experiment | None = None,
    use_rpm: bool = True,
    calibration: bool | structs.SimpleStirringCalibration | None = True,
    enable_dodging_od: bool = False,
    duty_cycle: float | None = None,
    target_rpm_during_od_reading: float | None = None,
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
        enable_dodging_od=enable_dodging_od,
        duty_cycle=duty_cycle,
        target_rpm_during_od_reading=target_rpm_during_od_reading,
    )
    return stirrer


@click.command(name="stirring")
@click.option(
    "--target-rpm",
    help="set the target RPM",
    show_default=True,
    type=click.FloatRange(0, MAX_TARGET_RPM, clamp=True),
)
@click.option("--use-rpm", type=click.BOOL, default=None, show_default=True, help="Use RPM feedback loop.")
@click.option(
    "--duty-cycle",
    type=click.FloatRange(0, 100),
    default=None,
    show_default=True,
    help="initial duty cycle (%)",
)
@click.option(
    "--target-rpm-during-od-reading",
    type=click.FLOAT,
    default=None,
    show_default=True,
    help="override RPM during OD readings",
)
@click.option(
    "--enable-dodging-od",
    type=click.BOOL,
    default=None,
    show_default=True,
)
@click.option(
    "--measure-rpm-only",
    is_flag=True,
    help="Measure and publish RPM without PID control. Duty cycle stays fixed.",
)
def click_stirring(
    target_rpm: float | None,
    use_rpm: bool | None,
    duty_cycle: float | None,
    target_rpm_during_od_reading: float | None,
    enable_dodging_od: bool | None,
    measure_rpm_only: bool,
) -> None:
    """
    Start the stirring of the Pioreactor.
    """
    if measure_rpm_only:
        target_rpm = None
        use_rpm = True
    else:
        if target_rpm is None:
            target_rpm = config.getfloat("stirring.config", "initial_target_rpm", fallback=500)
        use_rpm = (
            use_rpm
            if use_rpm is not None
            else config.getboolean("stirring.config", "use_rpm", fallback="true")
        )
    enable_dodging_od = (
        enable_dodging_od
        if enable_dodging_od is not None
        else config.getboolean("stirring.config", "enable_dodging_od", fallback="false")
    )
    try:
        with start_stirring(
            target_rpm=target_rpm,
            use_rpm=use_rpm,
            enable_dodging_od=enable_dodging_od,
            duty_cycle=duty_cycle,
            target_rpm_during_od_reading=target_rpm_during_od_reading,
        ) as st:
            st.block_until_rpm_is_close_to_target()
            st.block_until_disconnected()
    except exc.HardwareNotFoundError as e:
        from pioreactor.logging import create_logger

        create_logger("stirring").error(e)
