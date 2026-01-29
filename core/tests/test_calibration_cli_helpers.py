# -*- coding: utf-8 -*-
from __future__ import annotations

import click
from pioreactor.calibrations import cli_helpers


def test_action_block_outputs_lines_with_spacing(capsys) -> None:
    cli_helpers.action_block(["first", "second"])
    captured = click.unstyle(capsys.readouterr().out)
    assert captured == "\nfirst\nsecond\n\n"
