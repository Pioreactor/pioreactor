import React from "react";
import { render, screen, within } from "@testing-library/react";
import CalibrationSessionDataTable from "../components/CalibrationSessionDataTable";
import CalibrationSessionStepContent from "../components/CalibrationSessionStepContent";

test("formats numeric progress tables for any protocol while preserving labels and counts", () => {
  render(
    <CalibrationSessionStepContent
      step={{
        title: "Validation readings",
        metadata: {
          table: {
            columns: ["Capsule", "Reference pH", "Measured pH", "Absolute error"],
            rows: [["Low capsule", 2, 2.123456789, 0.00000123456789], ["High capsule", 11, 11, null]],
          },
        },
      }}
      loadingImages={[]}
    />,
  );

  expect(screen.getByText("Low capsule")).toBeVisible();
  expect(screen.getByText("2")).toBeVisible();
  expect(screen.getByText("2.123")).toBeVisible();
  expect(screen.getByText("1.23e-6")).toBeVisible();
  expect(screen.getByText("—")).toBeVisible();
});

test("review columns can override default precision without changing their recorded values", () => {
  const rows = [
    { run: 1, dc: 32.123456789, rpm: 502.123456789, duration: 1.23456789 },
    { run: 2, dc: 0, rpm: 0.00001, duration: null },
  ];
  render(
    <CalibrationSessionDataTable
      field={{ name: "readings", label: "Recorded readings", columns: [
        { key: "run", label: "Run" },
        { key: "dc", label: "Duty cycle (%)", precision: 2 },
        { key: "rpm", label: "RPM", precision: 1 },
        { key: "duration", label: "Duration (s)" },
      ] }}
      rows={rows}
    />,
  );

  const table = screen.getByRole("table", { name: "Recorded readings" });
  expect(within(table).getByText("1")).toBeVisible();
  expect(within(table).getByText("32.12")).toBeVisible();
  expect(within(table).getByText("502.1")).toBeVisible();
  expect(within(table).getByText("1.235")).toBeVisible();
  expect(within(table).getByText("0")).toBeVisible();
  expect(within(table).getByText("1.00e-5")).toBeVisible();
  expect(rows[0]).toEqual({ run: 1, dc: 32.123456789, rpm: 502.123456789, duration: 1.23456789 });
});
