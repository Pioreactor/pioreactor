# -*- coding: utf-8 -*-
from pioreactor.background_jobs.subjobs.dosing_automation import DosingAutomation
from pioreactor.dosing_automations import events
from pioreactor.utils.streaming_calculations import PID
from pioreactor.config import config


class PIDTurbidostat(DosingAutomation):
    """
    turbidostat mode - try to keep cell density constant using a PID target at the OD.

    The PID tells use what fraction of volume we should limit. For example, of PID
    returns 0.03, then we should remove ~97% of the volume. Choose volume to be about 1.5ml - 2.0ml.
    """

    key = "pid_turbidostat"

    def __init__(self, target_od=None, volume=None, **kwargs):
        super(PIDTurbidostat, self).__init__(**kwargs)
        assert target_od is not None, "`target_od` must be set"
        assert volume is not None, "`volume` must be set"
        self.set_target_od(target_od)
        self.volume = float(volume)

        # PID%20controller%20turbidostat.ipynb
        Kp = config.getfloat("dosing_automation.pid_turbidostat", "Kp")
        Ki = config.getfloat("dosing_automation.pid_turbidostat", "Ki")
        Kd = config.getfloat("dosing_automation.pid_turbidostat", "Kd")

        self.pid = PID(
            -Kp,
            -Ki,
            -Kd,
            setpoint=self.target_od,
            output_limits=(0, 1),
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="od",
        )

    def execute(self, *args, **kwargs) -> events.Event:
        if self.latest_od <= self.min_od:
            return events.NoEvent(
                f"current OD, {self.latest_od:.2f}, less than OD to start diluting, {self.min_od:.2f}"
            )
        else:
            output = self.pid.update(self.latest_od, dt=self.duration)

            volume_to_cycle = output * self.volume

            if volume_to_cycle < 0.01:
                return events.NoEvent(
                    f"PID output={output:.2f}, so practically no volume to cycle"
                )
            else:
                self.execute_io_action(media_ml=volume_to_cycle, waste_ml=volume_to_cycle)
                e = events.DilutionEvent(
                    f"PID output={output:.2f}, volume to cycle={volume_to_cycle:.2f}mL"
                )
                e.volume_to_cycle = volume_to_cycle
                e.pid_output = output
                return e

    @property
    def min_od(self):
        return 0.75 * self.target_od

    def set_target_od(self, value):
        self.target_od = float(value)
        try:
            # may not be defined yet...
            self.pid.set_setpoint(self.target_od)
        except AttributeError:
            pass
