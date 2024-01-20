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
    version: str  # can be a version, or version bound with version. Ex: "1.0.2", or ">=1.02", or "==1.0.2". See


######## Actions


class _LogOptions(Struct):
    message: str
    level: t.Literal[
        "DEBUG", "debug", "WARNING", "warning", "INFO", "info", "NOTICE", "notice", "ERROR", "error"
    ] = "notice"


class _Action(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    if_: str = field(name="if", default="True")


class Log(_Action, tag=str.lower, forbid_unknown_fields=True):
    options: _LogOptions = _LogOptions("<empty>", "DEBUG")


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


PioreactorUnitName = str
PioreactorLabel = str
JobName = str
Jobs = dict[JobName, dict[t.Literal["actions"], list[Action]]]


class PioreactorSpecific(Struct, forbid_unknown_fields=True):
    jobs: Jobs = {}
    label: t.Optional[str] = None
    # calibration_settings?
    # config_options?


class Common(Struct, forbid_unknown_fields=True):
    jobs: Jobs = {}


class Profile(Struct, forbid_unknown_fields=True):
    experiment_profile_name: str
    metadata: Metadata = field(default_factory=Metadata)
    plugins: list[Plugin] = []
    stop_on_exit: bool = False  # TODO: not implemented
    common: Common = field(default_factory=Common)  # later this might expand to include other fields
    pioreactors: dict[PioreactorUnitName, PioreactorSpecific] = {}
