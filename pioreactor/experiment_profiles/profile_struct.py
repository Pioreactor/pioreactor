# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

from msgspec import field
from msgspec import Struct


class Metadata(Struct):
    author: t.Optional[str] = None
    description: t.Optional[str] = None


class Plugin(Struct):
    name: str
    version: str  # can be a version, or version bound with version. Ex: "1.0.2", or ">=1.02", or "==1.0.2".


######## Actions


class _LogOptions(Struct):
    message: str
    level: t.Literal[
        "DEBUG", "debug", "WARNING", "warning", "INFO", "info", "NOTICE", "notice", "ERROR", "error"
    ] = "notice"


class Log(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    options: _LogOptions
    if_: t.Optional[str | bool] = field(name="if", default=None)

    def __str__(self):
        return f"Log(hours_elapsed={self.hours_elapsed:.5f}, message={self.options['message']})"


class _Action(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    if_: t.Optional[str | bool] = field(name="if", default=None)

    def __str__(self):
        return f"{self.__class__.__name__}(hours_elapsed={self.hours_elapsed:.5f})"


class Start(_Action, tag=str.lower, forbid_unknown_fields=True):
    options: dict[str, t.Any] = {}
    args: list[str] = []


class Pause(_Action, tag=str.lower, forbid_unknown_fields=True):
    pass


class Stop(_Action, tag=str.lower, forbid_unknown_fields=True):
    pass


class Update(_Action, tag=str.lower, forbid_unknown_fields=True):
    options: dict[str, t.Any] = {}


class Resume(_Action, tag=str.lower, forbid_unknown_fields=True):
    pass


Action = t.Union[Log, Start, Pause, Stop, Update, Resume]

#######


class Job(Struct, forbid_unknown_fields=True):
    actions: list[Action]
    # description?
    # metadata?
    # calibration_settings?
    # config_options?


PioreactorUnitName = str
PioreactorLabel = str
JobName = str
Jobs = dict[JobName, Job]


class PioreactorSpecificBlock(Struct, forbid_unknown_fields=True):
    jobs: Jobs = {}
    label: t.Optional[str] = None
    # calibration_settings?
    # config_options?
    # description?


class CommonBlock(Struct, forbid_unknown_fields=True):
    jobs: Jobs = {}


class Profile(Struct, forbid_unknown_fields=True):
    experiment_profile_name: str
    metadata: Metadata = field(default_factory=Metadata)
    plugins: list[Plugin] = []
    stop_on_exit: bool = False  # TODO: not implemented
    common: CommonBlock = field(
        default_factory=CommonBlock
    )  # later this might expand to include other fields
    pioreactors: dict[PioreactorUnitName, PioreactorSpecificBlock] = {}
