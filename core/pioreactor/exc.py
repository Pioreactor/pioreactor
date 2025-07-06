# -*- coding: utf-8 -*-
from __future__ import annotations


class PWMError(OSError):
    """
    Something went wrong with PWM outputs
    """


class HardwareNotFoundError(OSError):
    """
    A hardware device is missing.
    """


class JobRequiredError(Exception):
    """
    A job should be running, but isn't found.
    """


class JobPresentError(Exception):
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
