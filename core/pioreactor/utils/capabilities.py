# -*- coding: utf-8 -*-
"""Utility for introspecting combined job and action capabilities.

Example:
    python -m core.pioreactor.utils.capabilities --json
"""
from __future__ import annotations

import ast
import importlib
import inspect
import json
import pkgutil
from typing import Any
from typing import Dict
from typing import List

import click
import pioreactor
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.base import _BackgroundJob
from pioreactor.cli.run import run  # noqa: ensure commands and plugins are loaded


def _load_all_modules() -> None:
    """Import all modules under the ``pioreactor`` package."""

    for module in pkgutil.walk_packages(pioreactor.__path__, pioreactor.__name__ + "."):  # type: ignore
        try:
            importlib.import_module(module.name)
        except Exception:
            # ignore modules that fail to import
            pass


def _all_subclasses(cls: type) -> set[type]:
    subclasses = set()
    for sub in cls.__subclasses__():
        subclasses.add(sub)
        subclasses.update(_all_subclasses(sub))
    return subclasses


def _extract_additional_settings(cls: type) -> Dict[str, Dict[str, Any]]:
    """Parse class source for calls to ``add_to_published_settings``."""
    settings: Dict[str, Dict[str, Any]] = {}
    try:
        source = inspect.getsource(cls)
    except OSError:
        return settings

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "add_to_published_settings":
                if len(node.args) >= 2:
                    name_node = node.args[0]
                    data_node = node.args[1]
                    if isinstance(name_node, ast.Constant) and isinstance(name_node.value, str):
                        name = name_node.value
                        if isinstance(data_node, ast.Dict):
                            meta: Dict[str, Any] = {}
                            for k, v in zip(data_node.keys, data_node.values):
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    if isinstance(v, ast.Constant):
                                        meta[k.value] = v.value
                            settings[name] = meta
    return settings


def collect_background_jobs() -> List[Dict[str, Any]]:
    _load_all_modules()
    entries: List[Dict[str, Any]] = []
    for cls in _all_subclasses(_BackgroundJob):
        job_name = getattr(cls, "job_name", None)
        if not job_name or job_name == "background_job":
            continue

        settings = getattr(cls, "published_settings", {}).copy()
        settings.update(_extract_additional_settings(cls))

        if issubclass(cls, AutomationJob):
            automation_name = getattr(cls, "automation_name", None)
            if not automation_name or automation_name.endswith("_base"):
                continue
            cli_example = f"pio run {job_name} --automation-name {automation_name} --<settable param> <value>"
            entry: Dict[str, Any] = {
                "job_name": job_name,
                "automation_name": automation_name,
                "published_settings": settings,
                "cli_example": cli_example,
            }
        else:
            cli_example = f"pio run {job_name} --<settable param> <value>"
            entry = {
                "job_name": job_name,
                "published_settings": settings,
                "cli_example": cli_example,
            }
        entries.append(entry)

    # sort for consistent output
    entries.sort(key=lambda x: (x["job_name"], x.get("automation_name") or ""))
    return entries


def generate_command_metadata(cmd, name):
    entry: Dict[str, Any] = {
        "name": name,
        "help": (cmd.help or "").strip(),
        "arguments": [],
        "options": [],
    }

    for param in cmd.params:
        if isinstance(param, click.Argument):
            entry["arguments"].append(
                {
                    "name": param.name,
                    "nargs": param.nargs,
                    "required": param.required,
                    "type": getattr(param.type, "name", str(param.type)),
                }
            )
        elif isinstance(param, click.Option):
            entry["options"].append(
                {
                    "name": param.name,
                    "opts": param.opts,
                    "help": param.help or "",
                    "required": param.required,
                    "multiple": param.multiple,
                    # avoid click.get_default needing a Context (ctx=None would break)
                    "default": param.default,
                    "type": getattr(param.type, "name", str(param.type)),
                }
            )
    return entry


def collect_actions() -> List[Dict[str, Any]]:
    """Collect all subcommands under `pio run` and their parameters."""
    entries: List[Dict[str, Any]] = []
    for name, cmd in run.commands.items():
        if isinstance(cmd, click.Group):
            for sub_name, sub_cmd in cmd.commands.items():
                entries.append(generate_command_metadata(sub_cmd, name + " " + sub_name))
        else:
            entries.append(generate_command_metadata(cmd, name))

    return entries


def collect_capabilities() -> list[dict[str, Any]]:
    jobs = collect_background_jobs()
    actions = collect_actions()
    actions_map = {a["name"]: a for a in actions}

    caps: list[dict[str, Any]] = []

    # Collect merged metadata for each background job and its CLI interface.
    for job in jobs:
        name = job["job_name"]
        act = actions_map.get(name, {})
        # merge action metadata; for automations, filter out the automation_name option
        # start with declared options; for automations, strip --automation-name and add settable settings as flags
        opts = list(act.get("options", []))
        if job.get("automation_name"):
            opts = [o for o in opts if o.get("name") != "automation_name"]
            for setting, meta in job.get("published_settings", {}).items():
                if meta.get("settable"):
                    flag = setting.replace("_", "-")
                    opts.append(
                        {
                            "name": setting,
                            "opts": [f"--{flag}"],
                            "help": "",
                            "required": False,
                            "multiple": False,
                            "default": None,
                            "type": meta.get("datatype", "text"),
                        }
                    )
        entry: dict[str, Any] = {
            "job_name": name,
            **({"automation_name": job["automation_name"]} if job.get("automation_name") else {}),
            "help": act.get("help", ""),
            "arguments": act.get("arguments", []),
            "options": opts,
            "published_settings": job.get("published_settings", {}),
            "cli_example": job.get("cli_example", ""),
        }
        caps.append(entry)

    # also include any pio run actions that aren't background jobs (e.g. leader-only commands)
    job_names = {c["job_name"] for c in caps}
    for act in actions:
        name = act.get("name")
        if name not in job_names:
            arguments = act.get("arguments", [])
            caps.append(
                {
                    "job_name": name,
                    "help": act.get("help", ""),
                    "arguments": arguments,
                    "options": act.get("options", []),
                    "published_settings": {},
                    "cli_example": f"pio run {name} {' '.join([a['name'].upper() for a in arguments]) } [OPTIONS]",
                }
            )

    # sort for consistent output
    caps.sort(key=lambda x: (x["job_name"], x.get("automation_name") or ""))
    return caps


if __name__ == "__main__":
    click.echo(json.dumps(collect_capabilities(), indent=2))
