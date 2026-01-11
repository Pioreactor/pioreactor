# -*- coding: utf-8 -*-
from pioreactor.structs import AutomationEvent


class NoEvent(AutomationEvent):
    pass


class DilutionEvent(AutomationEvent):
    pass


class DosingStarted(AutomationEvent):
    pass


class DosingStopped(AutomationEvent):
    pass


class AddMediaEvent(AutomationEvent):
    pass


class AddAltMediaEvent(AutomationEvent):
    pass


class ChangedLedIntensity(AutomationEvent):
    pass


class ErrorOccurred(AutomationEvent):
    pass


class UpdatedHeaterDC(AutomationEvent):
    pass
