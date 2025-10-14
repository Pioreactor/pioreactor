# -*- coding: utf-8 -*-
"""
Registry of built-in and user-provided Pioreactor models.
"""
from __future__ import annotations

import os
from pathlib import Path

from msgspec import ValidationError
from msgspec.structs import replace
from msgspec.yaml import decode as yaml_decode
from pioreactor.structs import Model


def tag_latest(model: Model) -> Model:
    model.is_legacy = False
    return model


def tag_legacy(model: Model) -> Model:
    model.is_legacy = True
    return model


def tag_contrib(model: Model) -> Model:
    model.is_legacy = False
    model.is_contrib = True
    return model


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
    is_legacy=True,
    is_contrib=False,
)

PIOREACTOR_20ml__v1_1 = replace(
    PIOREACTOR_20ml__v1_0,
    model_version="1.1",
    display_name="Pioreactor 20ml, v1.1",
    max_temp_to_reduce_heating=78.0,
    max_temp_to_disable_heating=80.0,
    max_temp_to_shutdown=85.0,
    is_legacy=True,
)


PIOREACTOR_40ml__v1_0 = replace(
    PIOREACTOR_20ml__v1_1,
    model_version="1.0",
    display_name="Pioreactor 40ml, v1.0",
    model_name="pioreactor_40ml",
    reactor_capacity_ml=40.0,
    reactor_max_fill_volume_ml=38.0,
    is_legacy=True,
)


PIOREACTOR_20ml__v1_5 = replace(
    PIOREACTOR_20ml__v1_1,
    model_version="1.5",
    display_name="Pioreactor 20ml, v1.5",
    is_legacy=False,
)


PIOREACTOR_40ml__v1_5 = replace(
    PIOREACTOR_40ml__v1_0,
    model_version="1.5",
    display_name="Pioreactor 40ml, v1.5",
    is_legacy=False,
)


CORE_MODELS = {
    ("pioreactor_40ml", "1.5"): PIOREACTOR_40ml__v1_5,
    ("pioreactor_40ml", "1.0"): PIOREACTOR_40ml__v1_0,
    ("pioreactor_20ml", "1.5"): PIOREACTOR_20ml__v1_5,
    ("pioreactor_20ml", "1.1"): PIOREACTOR_20ml__v1_1,
    ("pioreactor_20ml", "1.0"): PIOREACTOR_20ml__v1_0,
}


def load_contrib_model_definitions() -> list[Model]:
    """Load all model definitions from YAML files under MODEL_DEFINITIONS_PATH."""

    MODEL_DEFINITIONS_PATH = Path(os.environ["DOT_PIOREACTOR"]) / "models"

    models: list[Model] = []
    if not MODEL_DEFINITIONS_PATH.exists():
        return models
    for file in MODEL_DEFINITIONS_PATH.glob("*.y*ml"):
        try:
            m = yaml_decode(file.read_bytes(), type=Model)
            models.append(tag_contrib(m))
        except ValidationError as e:
            from pioreactor.logging import create_logger

            create_logger("models", experiment="$experiment").error(
                f"Error loading model definition {file}: {e}"
            )
    return models


def get_registered_models() -> dict[tuple[str, str], Model]:
    # Merge built-in and user models, user overrides take priority
    registered_models = {
        **CORE_MODELS,
        **{(m.model_name, m.model_version): m for m in load_contrib_model_definitions()},
    }
    return registered_models
