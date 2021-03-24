# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events
from pioreactor.utils.streaming_calculations import PID
from pioreactor.config import config


VIAL_VOLUME = float(config["bioreactor"]["volume_ml"])


class PIDMorbidostat(DosingAutomation):
    """
    As defined in Zhong 2020
    """

    def __init__(self, target_growth_rate=None, target_od=None, volume=None, **kwargs):
        super(PIDMorbidostat, self).__init__(**kwargs)
        assert target_od is not None, "`target_od` must be set"
        assert target_growth_rate is not None, "`target_growth_rate` must be set"

        self.set_target_growth_rate(target_growth_rate)
        self.target_od = float(target_od)

        Kp = config.getfloat("pid_morbidostat", "Kp")
        Ki = config.getfloat("pid_morbidostat", "Ki")
        Kd = config.getfloat("pid_morbidostat", "Kd")

        self.pid = PID(
            -Kp,
            -Ki,
            -Kd,
            setpoint=self.target_growth_rate,
            output_limits=(0, 1),
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
        )

        if volume is not None:
            self.logger.info(
                "Ignoring volume parameter; volume set by target growth rate and duration."
            )

        self.volume = round(
            self.target_growth_rate * VIAL_VOLUME * (self.duration / 60), 4
        )

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od <= self.min_od:
            return events.NoEvent(
                f"latest OD less than OD to start diluting, {self.min_od:.2f}"
            )
        else:
            fraction_of_alt_media_to_add = self.pid.update(
                self.latest_growth_rate, dt=self.duration / 60
            )  # duration is measured in hours, not seconds (as simple_pid would want)

            # dilute more if our OD keeps creeping up - we want to stay in the linear range.
            if self.latest_od > self.max_od:
                self.logger.info(
                    f"executing triple dilution since we are above max OD, {self.max_od:.2f}AU."
                )
                volume = 2.5 * self.volume
            else:
                volume = self.volume

            alt_media_ml = fraction_of_alt_media_to_add * volume
            media_ml = (1 - fraction_of_alt_media_to_add) * volume

            self.execute_io_action(
                alt_media_ml=alt_media_ml, media_ml=media_ml, waste_ml=volume
            )
            event = events.AltMediaEvent(
                f"PID output={fraction_of_alt_media_to_add:.2f}, alt_media_ml={alt_media_ml:.2f}mL, media_ml={media_ml:.2f}mL"
            )
            event.media_ml = media_ml  # can be used for testing later
            event.alt_media_ml = alt_media_ml
            return event

    @property
    def min_od(self):
        return 0.7 * self.target_od

    @property
    def max_od(self):
        return 1.25 * self.target_od

    def set_target_growth_rate(self, value):
        self.target_growth_rate = float(value)
        try:
            self.pid.set_setpoint(self.target_growth_rate)
        except AttributeError:
            pass
