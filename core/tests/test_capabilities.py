# -*- coding: utf-8 -*-
"""
Tests for capability introspection utilities.
"""
from __future__ import annotations

import click
from pioreactor.utils.capabilities import _all_subclasses
from pioreactor.utils.capabilities import _extract_additional_settings
from pioreactor.utils.capabilities import collect_actions
from pioreactor.utils.capabilities import collect_capabilities
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


def test_collect_actions_includes_invokable_group(monkeypatch):
    # Group that is invokable without a subcommand should be included
    grp = click.Group("grp", help="grp help", invoke_without_command=True)
    grp.callback = lambda: None  # ensure it has a callback
    sub = click.Command("sub", help="sub help")
    grp.add_command(sub, "sub")
    monkeypatch.setattr(
        "pioreactor.utils.capabilities.run.commands",
        {"grp": grp},
    )
    actions = collect_actions()
    names = {a["name"] for a in actions}
    assert "grp" in names, "invokable group should be listed as an action"
    assert "grp sub" in names, "subcommands are still listed"


def test_capabilities_includes_od_blank_group_action():
    # Full collection should include the top-level od_blank action alongside its delete subcommand
    caps = collect_capabilities()
    names = {c["job_name"] for c in caps}
    assert "od_blank" in names, "od_blank group should be included as an action"
    # verify expected options are present
    odb = next(c for c in caps if c["job_name"] == "od_blank")
    option_names = {o["name"] for o in odb.get("options", [])}
    for expected in ("od_angle_channel1", "od_angle_channel2", "n_samples"):
        assert expected in option_names, f"missing option {expected} on od_blank"


def test_chemostat_inherits_parent_settings_and_options():
    # The 'chemostat' automation should include settings from its base class
    caps = collect_capabilities()
    chemo = next(c for c in caps if c.get("automation_name") == "chemostat")
    settings = set(chemo["published_settings"].keys())
    # parent settings from DosingAutomationJob base should be present
    for key in ("alt_media_fraction", "current_volume_ml", "max_working_volume_ml"):
        assert key in settings, f"{key} missing in published_settings for chemostat"

    # CLI options should also expose these settings as flags
    option_names = set(o["name"] for o in chemo.get("options", []))
    for key in ("alt_media_fraction", "current_volume_ml", "max_working_volume_ml", "exchange_volume_ml"):
        assert key in option_names, f"{key} missing in CLI options for chemostat"


def test_state_published_setting_for_all_jobs_and_not_in_cli_flags():
    """
    Verify that every job includes the "$state" published_setting, but that "$state" is not exposed
    as a CLI option for automations.
    """
    caps = collect_capabilities()
    for cap in caps:
        # Skip CLI-only actions (they have empty published_settings)
        if not cap["published_settings"]:
            continue
        # $state must be present in published_settings for all BackgroundJob-based entries
        assert (
            "$state" in cap["published_settings"]
        ), f"$state missing in published_settings for {cap['job_name']}"
        # For automations, $state should not appear as a CLI flag
        if cap.get("automation_name"):
            option_names = {o["name"] for o in cap.get("options", [])}
            assert (
                "$state" not in option_names
            ), f"$state should not be exposed as CLI option for automation {cap['automation_name']}"
