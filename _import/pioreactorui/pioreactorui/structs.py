# -*- coding: utf-8 -*-
from __future__ import annotations

import typing as t

from msgspec import Struct


#### Jobs


class PublishedSettingsDescriptor(Struct, forbid_unknown_fields=True):  # type: ignore
    key: str
    type: t.Literal["numeric", "boolean", "string", "json"]
    display: bool
    description: t.Optional[str] = None
    default: t.Optional[t.Union[str, bool]] = None  # DEPRECATED DO NOT USE
    unit: t.Optional[str] = None
    label: t.Optional[str] = None  # if display is false, this isn't needed
    editable: bool = True


class BackgroundJobDescriptor(Struct, forbid_unknown_fields=True):  # type: ignore
    display_name: str
    job_name: str
    display: bool
    published_settings: list[PublishedSettingsDescriptor]
    source: t.Optional[str] = None  # what plugin / app created this job? Usually `app`
    description: t.Optional[str] = None  # if display is false, this isn't needed
    subtext: t.Optional[str] = None
    is_testing: bool = False  # DEPRECATED DO NOT USE


#### Automations


class AutomationFieldsDescriptor(Struct, forbid_unknown_fields=True):  # type: ignore
    key: str
    default: t.Union[str, float, int, None]
    label: str
    disabled: bool = False
    unit: t.Optional[str] = None
    type: t.Literal["numeric", "string"] = "numeric"  # TODO we will include boolean


class AutomationDescriptor(Struct, forbid_unknown_fields=True):  # type: ignore
    display_name: str
    automation_name: str
    description: str
    source: t.Optional[str] = None  # what plugin / app created this automation? Usually `app`
    fields: list[AutomationFieldsDescriptor] = []


#### Charts


class ChartDescriptor(Struct, forbid_unknown_fields=True):  # type: ignore
    chart_key: str
    data_source: str  # SQL table
    title: str
    source: str
    y_axis_label: str
    fixed_decimals: int
    down_sample: bool = True
    mqtt_topic: t.Optional[str | list[str]] = None  # leave empty for no live updates from mqtt
    lookback: t.Union[int, str, float] = 100_000
    data_source_column: t.Optional[str] = None  # column in sql store
    payload_key: t.Optional[str] = None
    y_transformation: t.Optional[str] = "(y) => y"  # default is the identity
    y_axis_domain: t.Optional[list[float]] = None
    interpolation: t.Literal[
        "basis",
        "bundle",
        "cardinal",
        "catmullRom",
        "linear",
        "monotoneX",
        "monotoneY",
        "natural",
        "step",
        "stepAfter",
        "stepBefore",
    ] = "stepAfter"


class ArgsOptionsEnvs(Struct):
    options: dict[str, t.Any] = {}
    env: dict[str, str] = {}
    args: list[str] = []


class ArgsOptionsEnvsConfigOverrides(ArgsOptionsEnvs):
    config_overrides: list[list[str]] = []
