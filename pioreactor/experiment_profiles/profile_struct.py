# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

from msgspec import field
from msgspec import Struct


bool_expression = str | bool


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
    if_: t.Optional[bool_expression] = field(name="if", default=None)

    def __str__(self) -> str:
        return f"Log(hours_elapsed={self.hours_elapsed:.5f}, message={self.options.message})"


class _Action(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float
    if_: t.Optional[bool_expression] = field(name="if", default=None)

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(hours_elapsed={self.hours_elapsed:.5f})"


class Start(_Action):
    options: dict[str, t.Any] = {}
    args: list[str] = []


class Pause(_Action):
    pass


class Stop(_Action):
    pass


class Update(_Action):
    options: dict[str, t.Any] = {}


class Resume(_Action):
    pass


class When(_Action):
    condition: str = ""
    actions: list[Action] = []


class Repeat(_Action):
    repeat_every_hours: float = 1.0
    while_: t.Optional[str | bool] = field(name="while", default=None)
    max_hours: t.Optional[float] = None
    actions: list[BasicAction] = []
    _completed_loops: int = 0

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.hours_elapsed=:.5f}, {self.repeat_every_hours=}, {self.max_hours=}, {self.while_=})"


BasicAction = Log | Start | Pause | Stop | Update | Resume
Action = BasicAction | Repeat | When

#######


class Job(Struct, forbid_unknown_fields=True):
    actions: list[Action]
    description: t.Optional[str] = None
    # metadata?
    # calibration_settings?
    # config_options?
    # logging?


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
    common: CommonBlock = field(
        default_factory=CommonBlock
    )  # later this might expand to include other fields
    pioreactors: dict[PioreactorUnitName, PioreactorSpecificBlock] = {}
    inputs: dict[str, t.Any] = {}
