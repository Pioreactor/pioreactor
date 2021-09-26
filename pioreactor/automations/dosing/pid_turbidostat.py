# -*- coding: utf-8 -*-
from pioreactor.automations.dosing.base import DosingAutomation
from pioreactor.automations import events
from pioreactor.utils.streaming_calculations import PID
from pioreactor.config import config


class PIDTurbidostat(DosingAutomation):
    """
    turbidostat mode - try to keep cell density constant using a PID target at the OD.

    """

    key = "pid_turbidostat"

    published_settings = {
        "target_od": {"datatype": "float", "settable": True, "unit": "AU"},
        "duration": {"datatype": "float", "settable": True, "unit": "min"},
    }

    def __init__(self, target_od=None, **kwargs):
        super(PIDTurbidostat, self).__init__(**kwargs)
        assert target_od is not None, "`target_od` must be set"
        self.set_target_od(target_od)
        self.volume_to_cycle = None

        # PID%20controller%20turbidostat.ipynb
        Kp = config.getfloat("dosing_automation.pid_turbidostat", "Kp")
        Ki = config.getfloat("dosing_automation.pid_turbidostat", "Ki")
        Kd = config.getfloat("dosing_automation.pid_turbidostat", "Kd")

        self.pid = PID(
            -Kp,
            -Ki,
            -Kd,
            setpoint=self.target_od,
            sample_time=None,
            unit=self.unit,
            experiment=self.experiment,
            job_name=self.job_name,
            target_name="od",
        )

    def execute(self) -> events.Event:
        import numpy as np

        if self.latest_od <= self.min_od:
            return events.NoEvent(
                f"current OD, {self.latest_od:.2f}, less than OD to start diluting, {self.min_od:.2f}"
            )
        else:

            if self.volume_to_cycle is None:
                self.volume_to_cycle = (
                    14
                    - (
                        14
                        * np.exp(-(self.duration * self.latest_growth_rate) / 60)
                        * self.target_od
                    )
                    / self.latest_od
                )

            pid_output = self.pid.update(self.latest_od, dt=self.duration)
            self.volume_to_cycle = max(0, self.volume_to_cycle + pid_output)

            if self.volume_to_cycle < 0.01:
                return events.NoEvent("Practically no volume to cycle")
            else:
                volumes_actually_moved = self.execute_io_action(
                    media_ml=self.volume_to_cycle, waste_ml=self.volume_to_cycle
                )
                return events.DilutionEvent(
                    f"Volume cycled={volumes_actually_moved[0]:.2f}mL"
                )

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
