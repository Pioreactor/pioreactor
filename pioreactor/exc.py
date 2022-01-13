# -*- coding: utf-8 -*-


class HardwareNotFoundError(OSError):
    """
    A hardware device is missing.
    """


class JobRequiredError(Exception):
    """
    A job should be running, but isn't found.
    """
