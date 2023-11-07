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


class Log(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    options: _LogOptions


class Start(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    options: dict[str, t.Any] = {}
    args: list[str] = []


class Pause(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float


class Stop(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float


class Update(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    options: dict[str, t.Any] = {}


class Resume(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float


Action = t.Union[Log, Start, Pause, Stop, Update, Resume]

#######


PioreactorUnitName = str
PioreactorLabel = str
JobName = str
Jobs = dict[JobName, dict[t.Literal["actions"], list[Action]]]


class Profile(Struct, forbid_unknown_fields=True):
    experiment_profile_name: str
    metadata: Metadata = field(default_factory=Metadata)
    plugins: list[Plugin] = []
    stop_on_exit: bool = False
    labels: dict[PioreactorUnitName, PioreactorLabel] = {}
    common: Jobs = {}
    pioreactors: dict[
        t.Union[PioreactorLabel, PioreactorUnitName], dict[t.Literal["jobs"], Jobs]
    ] = {}
