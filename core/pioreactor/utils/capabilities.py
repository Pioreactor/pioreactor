# -*- coding: utf-8 -*-
"""Utility for introspecting combined job and action capabilities.

Example:
    python -m core.pioreactor.utils.capabilities

Rules summary for capability collection:
1. Discover all BackgroundJob subclasses (skip those without a valid job_name).
2. Merge each job class's static published_settings and dynamic add_to_published_settings calls across its MRO.
3. Always include a "$state" published setting (settable) for every BackgroundJob, but never expose it as a CLI flag.
4. Treat AutomationJob subclasses specially: skip base automations, require an automation_name, and build a dedicated CLI example with --automation-name.
5. Collect all `pio run` commands and subcommands, recording their arguments and options.
6. Merge background job metadata with CLI action metadata; for automations, strip the --automation-name option and add flags for settable settings.
7. Include any CLI-only actions (e.g. leader commands) even if no BackgroundJob exists, with empty published_settings.
8. Sort the final capabilities list by (job_name, automation_name) for consistent output.
"""
import ast
import importlib
import inspect
import json
import pkgutil
from functools import lru_cache
from types import MappingProxyType
from typing import Any
from typing import Dict
from typing import List
from typing import Tuple

import click
import pioreactor
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.base import _BackgroundJob
from pioreactor.cli.run import run


_MODULES_LOADED: bool = False


def _load_all_modules() -> None:
    """Import all modules under the ``pioreactor`` package once per process.

    Importing every module is expensive; many callers invoke capability
    collection repeatedly during a process lifetime. Cache that we've done the
    import sweep to avoid redundant work.
    """

    global _MODULES_LOADED
    if _MODULES_LOADED:
        return

    for module in pkgutil.walk_packages(pioreactor.__path__, pioreactor.__name__ + "."):  # type: ignore
        if module.name.startswith("pioreactor.web."):
            continue
        try:
            importlib.import_module(module.name)
        except Exception:
            # ignore modules that fail to import
            pass

    _MODULES_LOADED = True


def _all_subclasses(cls: type) -> set[type]:
    subclasses = set()
    for sub in cls.__subclasses__():
        subclasses.add(sub)
        subclasses.update(_all_subclasses(sub))
    return subclasses


def _extract_from_call_node(node: ast.Call) -> tuple[str, Dict[str, Any]] | None:
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr == "add_to_published_settings"):
        return None

    if len(node.args) < 2:
        return None

    name_node, data_node = node.args[0], node.args[1]
    if not (isinstance(name_node, ast.Constant) and isinstance(name_node.value, str)):
        return None

    if not isinstance(data_node, ast.Dict):
        return None

    meta: Dict[str, Any] = {}
    for key_node, value_node in zip(data_node.keys, data_node.values):
        if not (isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)):
            continue
        if isinstance(value_node, ast.Constant):
            meta[key_node.value] = value_node.value

    if not meta:
        return None

    return name_node.value, meta


def _extract_from_class_node(node: ast.ClassDef) -> Dict[str, Dict[str, Any]]:
    settings: Dict[str, Dict[str, Any]] = {}
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            extracted = _extract_from_call_node(child)
            if extracted:
                name, meta = extracted
                settings[name] = (
                    meta  # later occurrences override earlier ones, matching dict.update semantics
                )
    return settings


@lru_cache(maxsize=512)
def _module_additional_settings(source_path: str) -> MappingProxyType[str, Dict[str, Dict[str, Any]]]:
    try:
        with open(source_path, "r", encoding="utf-8") as fh:
            module_source = fh.read()
    except (OSError, FileNotFoundError):
        return MappingProxyType({})

    if "add_to_published_settings" not in module_source:
        return MappingProxyType({})

    try:
        tree = ast.parse(module_source, filename=source_path)
    except SyntaxError:
        return MappingProxyType({})

    collected: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def visit(node: ast.AST, parents: List[str]) -> None:
        if isinstance(node, ast.ClassDef):
            current = parents + [node.name]
            qualname = ".".join(current)
            collected[qualname] = _extract_from_class_node(node)
            for child in node.body:
                if isinstance(child, ast.ClassDef):
                    visit(child, current)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, current + [child.name, "<locals>"])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            new_parents = parents + [node.name, "<locals>"]
            for child in node.body:
                if isinstance(child, ast.ClassDef):
                    visit(child, new_parents)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit(child, new_parents)

    for top_level in getattr(tree, "body", []):
        if isinstance(top_level, ast.ClassDef):
            visit(top_level, [])
        elif isinstance(top_level, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit(top_level, [])

    return MappingProxyType(collected)


@lru_cache(maxsize=1024)
def _extract_additional_settings(cls: type) -> Dict[str, Dict[str, Any]]:
    """Parse class source for calls to ``add_to_published_settings`` with module-level caching."""

    try:
        source_path = inspect.getsourcefile(cls)
    except (OSError, TypeError):
        return {}

    if not source_path:
        return {}

    settings_map = _module_additional_settings(source_path)
    if not settings_map:
        return {}

    qualname = cls.__qualname__
    settings = settings_map.get(qualname)
    if not settings:
        return {}

    return dict(settings)


def collect_background_jobs() -> Tuple[Dict[str, Any], ...]:
    _load_all_modules()
    entries: List[Dict[str, Any]] = []
    for cls in _all_subclasses(_BackgroundJob):
        job_name = getattr(cls, "job_name", None)
        if not job_name or job_name == "background_job":
            continue

        # merge published_settings and add_to_published_settings calls from all ancestor classes
        settings: Dict[str, Dict[str, Any]] = {}
        for ancestor in reversed(cls.mro()):
            # static published_settings attr (may be None or empty)
            ancestor_settings = getattr(ancestor, "published_settings", {}) or {}
            settings.update(ancestor_settings)
            # dynamic settings added via add_to_published_settings in class source
            settings.update(_extract_additional_settings(ancestor))
        # always include the "$state" setting (settable) for every BackgroundJob, but never expose as CLI
        settings["$state"] = {"datatype": "text", "settable": True}

        if issubclass(cls, AutomationJob):
            automation_name = getattr(cls, "automation_name", None)
            if not automation_name or automation_name.endswith("_base"):
                continue
            cli_example = f"pio run {job_name} --automation-name {automation_name} [OPTIONS]"
            entry: Dict[str, Any] = {
                "job_name": job_name,
                "automation_name": automation_name,
                "published_settings": settings,
                "cli_example": cli_example,
            }
        else:
            cli_example = f"pio run {job_name} [OPTIONS]"
            entry = {
                "job_name": job_name,
                "published_settings": settings,
                "cli_example": cli_example,
            }
        entries.append(entry)

    # sort for consistent output
    entries.sort(key=lambda x: (x["job_name"], x.get("automation_name") or ""))
    # Return an immutable tuple for safe caching
    return tuple(entries)


def generate_command_metadata(cmd, name: str) -> Dict[str, Any]:
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
                    "long_flag": param.opts[0].lstrip("-"),
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
    if hasattr(run, "_load_plugins"):
        run._load_plugins()

    lazy_subcommands = getattr(run, "lazy_subcommands", {})
    for name in lazy_subcommands:
        cmd = run.get_command(None, name)
        if cmd is not None:
            run.commands[name] = cmd

    entries: List[Dict[str, Any]] = []
    for name, cmd in run.commands.items():
        if isinstance(cmd, click.Group):
            # Include the group itself if it is invokable without a subcommand
            # or has a callback defined (so `pio run <group>` is a valid action).
            if getattr(cmd, "invoke_without_command", False) or (getattr(cmd, "callback", None) is not None):
                entries.append(generate_command_metadata(cmd, name))

            # Also include each subcommand under the group.
            for sub_name, sub_cmd in cmd.commands.items():
                entries.append(generate_command_metadata(sub_cmd, name + " " + sub_name))
        else:
            entries.append(generate_command_metadata(cmd, name))

    return entries


def collect_capabilities() -> list[dict[str, Any]]:
    jobs = list(collect_background_jobs())
    actions = collect_actions()
    actions_map = {a["name"]: a for a in actions}

    caps: list[dict[str, Any]] = []

    # Collect merged metadata for each background job and its CLI interface.
    for job in jobs:
        name = job["job_name"]
        act = actions_map.get(name, {})
        # merge action metadata; for automations, filter out the automation_name option
        # start with declared options; for automations, strip --automation-name and add settable settings as flags
        options = list(act.get("options", []))
        if job.get("automation_name"):
            options = [o for o in options if o.get("name") != "automation_name"]

            for setting, meta in job.get("published_settings", {}).items():
                # skip internal $state even though it's settable
                if setting == "$state":
                    continue
                if setting in (o["name"] for o in options):
                    continue
                if meta.get("settable"):
                    flag = setting.replace("_", "-")
                    options.append(
                        {
                            "name": setting,
                            "long_flag": f"{flag}",
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
            "options": options,
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
                    "cli_example": f"pio run {name} {' '.join([a['name'].upper() for a in arguments]) }[OPTIONS]",
                }
            )

    # sort for consistent output
    caps.sort(key=lambda x: (x["job_name"], x.get("automation_name") or ""))
    return caps


if __name__ == "__main__":
    click.echo(json.dumps(collect_capabilities(), indent=2))
