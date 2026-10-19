# -*- coding: utf-8 -*-
"""
Shared "review data" step for calibration session flows.

Protocols that record data points end on a subclass of ReviewDataStep instead of saving
straight away. The step shows every recorded row in an editable table: the user can correct
values they typed in, leave rows out of the fit, preview the refit, and then save.
"""
from __future__ import annotations

from typing import Any

from pioreactor.calibrations.session_flow import CalibrationComplete
from pioreactor.calibrations.session_flow import fields
from pioreactor.calibrations.session_flow import SessionContext
from pioreactor.calibrations.session_flow import SessionStep
from pioreactor.calibrations.session_flow import steps
from pioreactor.calibrations.structured_session import CalibrationStep

REVIEW_TABLE_FIELD = "recorded_data"
PREVIEW_ACTION = "preview"
_EXCLUDED_ROWS_KEY = "review_excluded_rows"


def select_rows(values: list[Any], included: list[int]) -> list[Any]:
    return [values[index] for index in included]


def column(key: str, label: str, editable: bool = False, minimum: float | None = None) -> dict[str, Any]:
    return {"key": key, "label": label, "editable": editable, "minimum": minimum}


class ReviewDataStep(SessionStep):
    """
    Subclasses describe their table with `columns` and `rows`, write corrected values back in
    `apply_edits`, and persist in `save`. Rows are addressed by their position in `rows`.
    """

    step_id = "review_data"
    title = "Review data"
    body = (
        "Check the recorded data before saving. Correct any value you typed in, or uncheck a row "
        "to leave it out of the fit."
    )
    save_label = "Save calibration"
    # Label of the button that re-renders the step with the edits applied, or None to hide it.
    preview_label: str | None = "Update chart"
    # Set False when every row is required, e.g. a protocol with a fixed number of standards.
    allow_exclude = True
    minimum_included_rows = 2

    def columns(self, ctx: SessionContext) -> list[dict[str, Any]]:
        raise NotImplementedError

    def rows(self, ctx: SessionContext) -> list[dict[str, Any]]:
        raise NotImplementedError

    def apply_edits(self, ctx: SessionContext, index: int, row: dict[str, Any]) -> None:
        """Write the editable values of row `index` back into ctx.data."""

    def chart(self, ctx: SessionContext, included: list[int]) -> dict[str, Any] | None:
        return None

    def summary(self, ctx: SessionContext, included: list[int]) -> str | None:
        return None

    def save(self, ctx: SessionContext, included: list[int]) -> None:
        """Fit using only the `included` rows, store the result, and call ctx.complete(...)."""
        raise NotImplementedError

    def included_rows(self, ctx: SessionContext) -> list[int]:
        excluded = set(ctx.data.get(_EXCLUDED_ROWS_KEY, []))
        return [index for index in range(len(self.rows(ctx))) if index not in excluded]

    def render(self, ctx: SessionContext) -> CalibrationStep:
        included = self.included_rows(ctx)
        table_rows = []
        for index, row in enumerate(self.rows(ctx)):
            if self.allow_exclude:
                row = {**row, "include": index in included}
            table_rows.append(row)

        body = self.body
        if self.preview_label:
            body = f"{body} Press {self.preview_label} to preview your changes."
        summary = self.summary(ctx, included)
        if summary:
            body = f"{body}\n\n{summary}"

        step = steps.form(
            self.title,
            body,
            [fields.data_table(REVIEW_TABLE_FIELD, self.columns(ctx), table_rows, label="Recorded data")],
        )
        step.metadata = {
            "primary_action_label": self.save_label,
            "dialog": {"max_width": "md", "height": 760},
        }
        if self.preview_label:
            step.metadata["actions"] = [
                {"label": self.preview_label, "inputs": {"action": PREVIEW_ACTION}, "include_values": True}
            ]
        chart = self.chart(ctx, included)
        if chart:
            step.metadata["chart"] = chart
        return step

    def advance(self, ctx: SessionContext) -> SessionStep | None:
        edited_rows = ctx.inputs.data_table(REVIEW_TABLE_FIELD, self.columns(ctx))
        if len(edited_rows) != len(self.rows(ctx)):
            raise ValueError("The recorded data changed while reviewing. Reload the session and try again.")

        for index, row in enumerate(edited_rows):
            self.apply_edits(ctx, index, row)
        ctx.data[_EXCLUDED_ROWS_KEY] = [
            index for index, row in enumerate(edited_rows) if self.allow_exclude and not row["include"]
        ]

        if ctx.inputs.raw and ctx.inputs.raw.get("action") == PREVIEW_ACTION:
            return None

        included = self.included_rows(ctx)
        if len(included) < self.minimum_included_rows:
            raise ValueError(f"Keep at least {self.minimum_included_rows} rows to fit a calibration.")
        self.save(ctx, included)
        return CalibrationComplete()
