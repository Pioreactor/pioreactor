# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

from msgspec import Struct


class Metadata(Struct):
    author: str
    description: str
    media_used: t.Optional[str] = None
    organism_used: t.Optional[str] = None


class Plugin(Struct):
    name: str
    version: str


class Action(Struct):
    type: t.Literal["start", "pause", "resume", "stop", "update"]
    duration: float
    parameters: t.Optional[dict[str, t.Any]] = None


BioreactorName = str
BioreactorAlias = str
JobName = str
Jobs = dict[JobName, dict[t.Literal["actions"], list[Action]]]


class Profile(Struct):
    experiment_name: str
    metadata: Metadata
    plugins: list[Plugin]
    aliases: dict[BioreactorName, BioreactorAlias]
    global_jobs: Jobs
    bioreactors: dict[BioreactorAlias | BioreactorName, dict[t.Literal["jobs"], Jobs]]
