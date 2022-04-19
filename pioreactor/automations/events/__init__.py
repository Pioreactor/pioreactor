# -*- coding: utf-8 -*-
from __future__ import annotations

from pioreactor.structs import AutomationEvent


class NoEvent(AutomationEvent):
    pass


class DilutionEvent(AutomationEvent):
    pass


class AddMediaEvent(AutomationEvent):
    pass


class AddAltMediaEvent(AutomationEvent):
    pass


class ChangedLedIntensity(AutomationEvent):
    pass


class RunningContinuously(AutomationEvent):
    pass


class ErrorOccurred(AutomationEvent):
    pass


class UpdatedHeaterDC(AutomationEvent):
    pass
