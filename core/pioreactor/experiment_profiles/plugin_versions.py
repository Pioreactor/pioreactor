# -*- coding: utf-8 -*-
import re

from packaging.specifiers import InvalidSpecifier
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import Version


SUPPORTED_PLUGIN_VERSION_CONSTRAINT = re.compile(r"(==|>=|<=)?(.+)")


def parse_plugin_version_constraint(value: str) -> SpecifierSet:
    constraint = value.strip()
    match = SUPPORTED_PLUGIN_VERSION_CONSTRAINT.fullmatch(constraint)
    if match is None:
        raise InvalidSpecifier(f"Invalid plugin version constraint: {value!r}")

    operator, version = match.groups()
    try:
        Version(version)
    except InvalidVersion as exc:
        raise InvalidSpecifier(f"Invalid plugin version constraint: {value!r}") from exc

    return SpecifierSet(f"{operator or '=='}{version}")
