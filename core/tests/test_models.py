# -*- coding: utf-8 -*-
from pathlib import Path

import pytest
from pioreactor.models import CORE_MODELS
from pioreactor.models import get_registered_models

CUSTOM_MODEL = """\
model_name: custom_bench_reactor
model_version: "0.1"
display_name: Custom bench reactor
reactor_capacity_ml: 30.0
reactor_diameter_mm: 27.0
reactor_max_fill_volume_ml: 28.0
max_temp_to_reduce_heating: 63.0
max_temp_to_disable_heating: 65.0
max_temp_to_shutdown: 66.0
"""


@pytest.mark.parametrize("make_bad_file", ["syntax_error", "dangling_symlink"])
def test_one_bad_model_definition_does_not_hide_the_others(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_bad_file: str
) -> None:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "custom.yaml").write_text(CUSTOM_MODEL, encoding="utf-8")
    if make_bad_file == "syntax_error":
        (models_dir / "broken.yaml").write_text("model_name: [\n", encoding="utf-8")
    else:
        (models_dir / "broken.yaml").symlink_to(tmp_path / "missing.yaml")
    monkeypatch.setenv("DOT_PIOREACTOR", tmp_path.as_posix())

    registered_models = get_registered_models()

    assert ("custom_bench_reactor", "0.1") in registered_models
    assert all((m.model_name, m.model_version) in registered_models for m in CORE_MODELS)
