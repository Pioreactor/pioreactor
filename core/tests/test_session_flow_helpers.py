# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from pioreactor.calibrations import session_flow
from pioreactor.calibrations.structured_session import CalibrationStepField


def test_step_id_from_rejects_invalid_steps() -> None:
    class InvalidStep(session_flow.SessionStep):
        step_id = ""

    with pytest.raises(ValueError, match="Invalid step identifier"):
        session_flow._step_id_from(InvalidStep())


def test_validate_field_bounds_uses_custom_max_error() -> None:
    fields = [
        CalibrationStepField(
            name="count",
            label="count",
            field_type="int",
            minimum=1,
            maximum=3,
            max_error_msg="Too many",
        )
    ]

    with pytest.raises(ValueError, match="Too many"):
        session_flow._validate_field_bounds(fields, {"count": 5})
