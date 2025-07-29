# -*- coding: utf-8 -*-
"""Utility for introspecting BackgroundJob subclasses."""
from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

import click
import pioreactor
from pioreactor.automations.base import AutomationJob
from pioreactor.background_jobs.base import _BackgroundJob


def _load_all_modules() -> None:
    """Import all modules under the ``pioreactor`` package."""

    plugins_dev = Path("plugins_dev").resolve()

    for module in pkgutil.walk_packages(pioreactor.__path__, pioreactor.__name__ + "."):  # type: ignore
        # skip any modules that originate from plugins_dev
        if plugins_dev in Path(module.module_finder.path).resolve().parents:  # type: ignore
            continue

        try:
            importlib.import_module(module.name)
        except Exception:
            # ignore modules that fail to import
            pass


def _all_subclasses(cls: type) -> set[type]:
    subclasses = set()
    for sub in cls.__subclasses__():
        if sub.__qualname__.endswith("Contrib"):
            continue
        # print(sub.__qualname__)
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
    merged: Dict[str, Any] = {}
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
            job_entry = merged.setdefault(job_name, {"automations": {}})
            # add a CLI usage example for this job
            job_entry[
                "cli_example"
            ] = f"pio run {job_name} --automation-name {automation_name} --<param> <value>"
            auto_entry = job_entry["automations"].setdefault(automation_name, {})
            for key, meta in settings.items():
                auto_entry.setdefault(key, meta)
        else:
            job_entry = merged.setdefault(job_name, {"published_settings": {}})
            # add a CLI usage example for this job
            job_entry["cli_example"] = f"pio run {job_name} --<param> <value>"
            pub = job_entry["published_settings"]
            for key, meta in settings.items():
                pub.setdefault(key, meta)

    output: List[Dict[str, Any]] = []
    for name, info in merged.items():
        if "automations" in info:
            automations = [
                {
                    "automation_name": auto_name,
                    "published_settings": settings,
                }
                for auto_name, settings in info["automations"].items()
            ]
            entry: Dict[str, Any] = {"job_name": name, "automations": automations}
        else:
            entry = {"job_name": name, "published_settings": info["published_settings"]}
        # include cli_example if available
        if "cli_example" in info:
            entry["cli_example"] = info["cli_example"]
        output.append(entry)

    return output


@click.command()
@click.option("--json", "json_output", is_flag=True, help="output as JSON")
def main(json_output: bool) -> None:
    """List BackgroundJob subclasses and their settings."""
    import json

    info = collect_background_jobs()
    if json_output:
        click.echo(json.dumps(info, indent=2))
    else:
        for job in info:
            click.echo(job["job_name"])
            if "automations" in job:
                for auto in job["automations"]:
                    click.echo(f"  automation: {auto['automation_name']}")
                    for setting, meta in auto["published_settings"].items():
                        click.echo(f"    - {setting}: {meta}")
            else:
                for setting, meta in job["published_settings"].items():
                    click.echo(f"  - {setting}: {meta}")
            click.echo()


if __name__ == "__main__":
    main()
