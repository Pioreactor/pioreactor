# -*- coding: utf-8 -*-
import typing as t

from msgspec import field
from msgspec import Struct
from pioreactor import types as pt


bool_expression = str | bool


class Metadata(Struct):
    author: str | None = None
    description: str | None = None


class Plugin(Struct):
    name: str
    version: str  # can be a version, or version bound with version. Ex: "1.0.2", or ">=1.02", or "==1.0.2".


######## Actions


class _LogOptions(Struct):
    message: str
    level: t.Literal[
        "DEBUG", "debug", "WARNING", "warning", "INFO", "info", "NOTICE", "notice", "ERROR", "error"
    ] = "NOTICE"


class Log(Struct, tag=str.lower, forbid_unknown_fields=True):
    options: _LogOptions
    if_: bool_expression = field(name="if", default=True)
    hours_elapsed: float | None = None
    t: str | float | None = None

    def __str__(self) -> str:
        return f"Log(message={self.options.message})"


class _Action(Struct, tag=str.lower, forbid_unknown_fields=True):
    hours_elapsed: float | None = None
    t: str | float | None = None
    if_: bool_expression = field(name="if", default=True)

    def __str__(self) -> str:
        return f"{self.__class__.__name__.lower()}"


class _ContainerAction(_Action):
    pass


class Start(_Action):
    options: dict[str, t.Any] = {}
    args: list[str] = []
    config_overrides: dict[str, t.Any] = {}


class Pause(_Action):
    pass


class Stop(_Action):
    pass


class Update(_Action):
    options: dict[str, t.Any] = {}


class Resume(_Action):
    pass


class When(_ContainerAction):
    condition_: str = field(name="condition", default="")
    wait_until: str = field(name="wait_until", default="")
    actions: list["Action"] = []


class Repeat(_ContainerAction):
    repeat_every_hours: float | None = None
    every: float | str | None = None
    while_: str | bool = field(name="while", default=True)
    max_hours: float | None = None
    max_time: float | str | None = None
    actions: list["BasicAction"] = []
    _completed_loops: int = 0


BasicAction = Log | Start | Pause | Stop | Update | Resume
ContainerAction = Repeat | When
Action = BasicAction | ContainerAction

#######


class Job(Struct, forbid_unknown_fields=True):
    actions: list[Action]
    description: str | None = None
    # metadata?
    # calibration_settings?
    # config_options?
    # logging?


PioreactorUnitName = pt.Unit
PioreactorLabel = str
JobName = str
Jobs = dict[JobName, Job]


class PioreactorSpecificBlock(Struct, forbid_unknown_fields=True):
    jobs: Jobs = {}
    label: str | None = None
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
