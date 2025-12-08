# -*- coding: utf-8 -*-
from __future__ import annotations


class PWMError(OSError):
    """
    Something went wrong with PWM outputs
    """


class HardwareError(OSError):
    """
    A hardware device error
    """


class HardwareNotFoundError(HardwareError):
    """
    A hardware device is missing.
    """


class JobRequiredError(RuntimeError):
    """
    A job should be running, but isn't found.
    """


class JobPresentError(RuntimeError):
    """
    A job shouldn't be running, but is.
    """


class CalibrationError(Exception):
    """
    An issue with calibration (pump, stirring, OD, etc.)
    """


class NotActiveWorkerError(Exception):
    """
    if a worker is not active, things shouldn't happen.
    """


class NotAssignedAnExperimentError(Exception):
    """
    if a worker is assigned an experiment, and something is trying to run
    """


class NoWorkerFoundError(Exception):
    """
    Worker isn't present in the leader's inventory
    """


class BashScriptError(Exception):
    """
    Some external bash script failed
    """


class RoleError(Exception):
    """
    Leader vs worker?
    """


class MQTTValueError(ValueError):
    """
    Data from MQTT is not expected / correct
    """


class RsyncError(OSError):
    """
    Syncing files failed
    """


class SSHError(OSError):
    """
    SSH command failed
    """


class NoSolutionsFoundError(ValueError):
    """
    No solutions found
    """


class SolutionBelowDomainError(ValueError):
    """
    Outside minimum range
    """


class SolutionAboveDomainError(ValueError):
    """
    Outside maximum range
    """


class NoModelAssignedError(ValueError):
    """
    The model is not provided to this Pioreactor.
    """


class UnknownModelAssignedError(ValueError):
    """
    The model isn't present in the registered models in models.py
    """


class DodgingTimingError(RuntimeError):
    pass
