# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor import types as pt
from pioreactor.utils import od_fusion


def test_fit_fusion_model_requires_records() -> None:
    with pytest.raises(ValueError, match="No usable fusion calibration records"):
        od_fusion.fit_fusion_model([])


def test_fit_fusion_model_missing_angle_raises() -> None:
    records: list[tuple[pt.PdAngle, float, float]] = [("45", conc, 0.5) for conc in [0.1, 0.2, 0.3, 0.4]]

    with pytest.raises(ValueError, match="Missing fusion calibration data for angle 90"):
        od_fusion.fit_fusion_model(records)
