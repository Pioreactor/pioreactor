# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor import estimators as estimators_module


def _patch_estimator_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(estimators_module, "ESTIMATOR_PATH", tmp_path)


def test_list_estimator_devices_empty_returns_empty(tmp_path, monkeypatch) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    assert estimators_module.list_estimator_devices() == []


def test_load_estimator_missing_file_raises(tmp_path, monkeypatch) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    with pytest.raises(FileNotFoundError, match="was not found"):
        estimators_module.load_estimator("od_fused", "missing")


def test_load_estimator_empty_file_raises(tmp_path, monkeypatch) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    device_dir = tmp_path / "od_fused"
    device_dir.mkdir(parents=True)
    (device_dir / "empty.yaml").write_text("")

    with pytest.raises(FileNotFoundError, match="is empty"):
        estimators_module.load_estimator("od_fused", "empty")


def test_load_estimator_invalid_yaml_raises(tmp_path, monkeypatch) -> None:
    _patch_estimator_path(tmp_path, monkeypatch)

    device_dir = tmp_path / "od_fused"
    device_dir.mkdir(parents=True)
    (device_dir / "bad.yaml").write_text("foo: bar\n")

    with pytest.raises(Exception, match="Error reading bad"):
        estimators_module.load_estimator("od_fused", "bad")
