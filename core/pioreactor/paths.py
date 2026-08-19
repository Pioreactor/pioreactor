# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path

from pioreactor.whoami import is_testing_env


def get_dot_pioreactor_path() -> Path:
    if configured_path := os.environ.get("DOT_PIOREACTOR"):
        return Path(configured_path)

    if is_testing_env():
        return Path(".pioreactor")

    return Path("/home/pioreactor/.pioreactor")


def get_run_pioreactor_path() -> Path:
    return Path(os.environ.get("RUN_PIOREACTOR", "/run/pioreactor"))


def get_pio_venv_path() -> Path:
    return Path(os.environ.get("PIO_VENV", "/opt/pioreactor/venv"))
