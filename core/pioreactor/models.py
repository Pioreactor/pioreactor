# -*- coding: utf-8 -*-
"""
Registry of built-in and user-provided Pioreactor models.
"""
from __future__ import annotations

import os
from pathlib import Path

from msgspec import ValidationError
from msgspec.yaml import decode as yaml_decode
from pioreactor.structs import Model
from pioreactor.whoami import is_testing_env


## Built-in Pioreactor models with hard-coded defaults

PIOREACTOR_20ml__v1_0 = Model(
    model_name="pioreactor_20ml",
    model_version="1.0",
    display_name="Pioreactor 20ml, v1.0",
    reactor_capacity_ml=20.0,
    reactor_max_fill_volume_ml=18.0,
    reactor_diameter_mm=27.0,
    max_temp_to_reduce_heating=63.0,
    max_temp_to_disable_heating=65.0,
    max_temp_to_shutdown=66.0,
)

PIOREACTOR_20ml__v1_1 = Model(
    model_name="pioreactor_20ml",
    model_version="1.1",
    display_name="Pioreactor 20ml, v1.1",
    reactor_capacity_ml=20.0,
    reactor_max_fill_volume_ml=18.0,
    reactor_diameter_mm=27.0,
    max_temp_to_reduce_heating=78.0,
    max_temp_to_disable_heating=80.0,
    max_temp_to_shutdown=85.0,
)

PIOREACTOR_40ml__v1_0 = Model(
    model_name="pioreactor_40ml",
    model_version="1.0",
    display_name="Pioreactor 40ml, v1.0",
    reactor_capacity_ml=40.0,
    reactor_max_fill_volume_ml=38.0,
    reactor_diameter_mm=27.0,
    max_temp_to_reduce_heating=78.0,
    max_temp_to_disable_heating=80.0,
    max_temp_to_shutdown=85.0,
)

CORE_MODELS = {
    ("pioreactor_20ml", "1.0"): PIOREACTOR_20ml__v1_0,
    ("pioreactor_20ml", "1.1"): PIOREACTOR_20ml__v1_1,
    ("pioreactor_40ml", "1.0"): PIOREACTOR_40ml__v1_0,
}


def load_contrib_model_definitions() -> list[Model]:
    """Load all model definitions from YAML files under MODEL_DEFINITIONS_PATH."""

    if not is_testing_env():
        MODEL_DEFINITIONS_PATH = Path("/home") / "pioreactor" / ".pioreactor" / "models"
    else:
        MODEL_DEFINITIONS_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "models"

    models: list[Model] = []
    if not MODEL_DEFINITIONS_PATH.exists():
        return models
    for file in MODEL_DEFINITIONS_PATH.glob("*.y*ml"):
        try:
            m = yaml_decode(file.read_bytes(), type=Model)
            models.append(m)
        except ValidationError as e:
            from pioreactor.logging import create_logger

            create_logger("models", experiment="$experiment").error(
                f"Error loading model definition {file}: {e}"
            )
    return models


# Merge built-in and user models, user overrides take priority
registered_models: dict[tuple[str, str], Model] = {
    **CORE_MODELS,
    **{(m.model_name, m.model_version): m for m in load_contrib_model_definitions()},
}
