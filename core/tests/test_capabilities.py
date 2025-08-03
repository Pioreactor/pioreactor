# -*- coding: utf-8 -*-
"""
Tests for capability introspection utilities.
"""
from __future__ import annotations

import click
from pioreactor.utils.capabilities import _all_subclasses
from pioreactor.utils.capabilities import _extract_additional_settings
from pioreactor.utils.capabilities import collect_actions
from pioreactor.utils.capabilities import generate_command_metadata


def test_all_subclasses():
    class Base:
        pass

    class A(Base):
        pass

    class B(A):
        pass

    subs = _all_subclasses(Base)
    assert A in subs
    assert B in subs


class DummySettings:
    def foo(self):
        # second arg must be dict of constants
        self.add_to_published_settings("nope", [1, 2, 3])
        self.add_to_published_settings("yes", {"a": 1, "b": "two"})
        # nested dict values are not constants and should be ignored
        self.add_to_published_settings("partial", {"x": True, "y": {"z": 3}})


def test_extract_additional_settings():
    settings = _extract_additional_settings(DummySettings)
    # only 'yes' and 'partial' keys are captured
    assert "yes" in settings and settings["yes"] == {"a": 1, "b": "two"}
    assert "nope" not in settings
    assert "partial" in settings and settings["partial"] == {"x": True}


def test_generate_command_metadata():
    arg = click.Argument(["arg"], nargs=1, required=True, type=click.INT)
    opt = click.Option(
        ["--opt", "-o"], help="option help", required=False, multiple=True, default=["foo"], type=click.STRING
    )
    cmd = click.Command("cmd", params=[arg, opt], help="cmd help")
    entry = generate_command_metadata(cmd, "cmd")
    assert entry["name"] == "cmd"
    assert entry["help"] == "cmd help"
    assert entry["arguments"] == [
        {
            "name": "arg",
            "nargs": 1,
            "required": True,
            "type": "integer",
        }
    ]
    assert entry["options"] == [
        {
            "name": "opt",
            "long_flag": "opt",
            "help": "option help",
            "required": False,
            "multiple": True,
            "default": ["foo"],
            "type": "text",
        }
    ]


def test_collect_actions(monkeypatch):
    # prepare fake commands mapping
    arg = click.Argument(["arg"], nargs=2, required=False, type=click.STRING)
    opt = click.Option(["--opt"], help=None, required=True, multiple=False, default=None, type=click.INT)
    cmd1 = click.Command("foo", params=[arg, opt], help="foo help")
    grp = click.Group("grp", help="grp help")
    sub = click.Command("sub", params=[opt], help="sub help")
    grp.add_command(sub, "sub")
    monkeypatch.setattr(
        "pioreactor.utils.capabilities.run.commands",
        {"foo": cmd1, "grp": grp},
    )
    actions = collect_actions()
    names = [a["name"] for a in actions]
    # expect both standalone and subcommands
    assert "foo" in names
    assert "grp sub" in names
    # verify metadata for foo
    foo = next(a for a in actions if a["name"] == "foo")
    assert foo["help"] == "foo help"
    assert foo["arguments"][0]["name"] == "arg"
    assert foo["options"][0]["name"] == "opt"
