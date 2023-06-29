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


class Action(Struct, forbid_unknown_fields=True):
    type: t.Literal["start", "pause", "resume", "stop", "update"]
    hours_elapsed: float
    options: dict[str, t.Any] = {}
    args: list[str] = []


PioreactorUnitName = str
PioreactorLabel = str
JobName = str
Jobs = dict[JobName, dict[t.Literal["actions"], list[Action]]]


class Profile(Struct):
    experiment_profile_name: str
    metadata: Metadata = field(default_factory=Metadata)
    plugins: list[Plugin] = []
    labels: dict[PioreactorUnitName, PioreactorLabel] = {}
    common: Jobs = {}
    pioreactors: dict[
        t.Union[PioreactorLabel, PioreactorUnitName], dict[t.Literal["jobs"], Jobs]
    ] = {}
