# -*- coding: utf-8 -*-
"""Utility for introspecting `pio run` subcommands and their parameters.

Example:
    python -m core.pioreactor.utils.action_inspector --json
"""
from __future__ import annotations

import json
from typing import Any
from typing import Dict
from typing import List

import click
from pioreactor.cli.run import run  # noqa: ensure commands and plugins are loaded


def collect_actions() -> List[Dict[str, Any]]:
    """Collect all subcommands under `pio run` and their parameters."""
    entries: List[Dict[str, Any]] = []
    for name, cmd in sorted(run.commands.items(), key=lambda x: x[0]):
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

        entries.append(entry)
    return entries


@click.command()
@click.option("--json", "json_output", is_flag=True, help="output as JSON")
def main(json_output: bool) -> None:
    """List `pio run` subcommands and their args/options."""
    info = collect_actions()
    if json_output:
        click.echo(json.dumps(info, indent=2))
    else:
        for cmd in info:
            click.echo(f"Command: {cmd['name']}")
            if cmd["help"]:
                click.echo(f"  Help: {cmd['help']}")
            click.echo(f"  Example: {cmd['cli_example']}")
            if cmd["arguments"]:
                click.echo("  Arguments:")
                for arg in cmd["arguments"]:
                    click.echo(
                        f"    - name: {arg['name']}, nargs: {arg['nargs']}, required: {arg['required']}, type: {arg['type']}"
                    )
            if cmd["options"]:
                click.echo("  Options:")
                for opt in cmd["options"]:
                    click.echo(
                        f"    - name: {opt['name']}, opts: {opt['opts']}, required: {opt['required']}, multiple: {opt['multiple']}, default: {opt['default']}, type: {opt['type']}, help: {opt['help']}"
                    )
            click.echo()


if __name__ == "__main__":
    main()
