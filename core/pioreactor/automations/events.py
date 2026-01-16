# -*- coding: utf-8 -*-
from pioreactor.structs import AutomationEvent


class NoEvent(AutomationEvent, tag="NoEvent"):
    pass


class DilutionEvent(AutomationEvent, tag="DilutionEvent"):
    pass


class DosingStarted(AutomationEvent, tag="DosingStarted"):
    pass


class DosingStopped(AutomationEvent, tag="DosingStopped"):
    pass


class AddMediaEvent(AutomationEvent, tag="AddMediaEvent"):
    pass


class AddAltMediaEvent(AutomationEvent, tag="AddAltMediaEvent"):
    pass


class ChangedLedIntensity(AutomationEvent, tag="ChangedLedIntensity"):
    pass


class ErrorOccurred(AutomationEvent, tag="ErrorOccurred"):
    pass


class UpdatedHeaterDC(AutomationEvent, tag="UpdatedHeaterDC"):
    pass
