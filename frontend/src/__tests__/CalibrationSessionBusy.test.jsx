import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const CalibrationSessionDialog = require("../components/CalibrationSessionDialog").default;
const CalibrationSessionFields = require("../components/CalibrationSessionFields").default;

test.each([false, true])("locks the sample OD while recording and recovers after failure=%s", async (fails) => {
  const step = {
    step_id: "measure_standard",
    step_type: "form",
    title: "Record standard 2 of 3",
    fields: [{ name: "od600_value", label: "OD600 value", field_type: "float", default: 0.5 }],
    metadata: { primary_action_label: "Measure standard" },
  };
  let finish;
  const pending = new Promise((resolve) => { finish = resolve; });
  global.fetch = jest.fn((url) => {
    if (url.endsWith("/inputs")) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ task_id: "recording" }) });
    }
    if (url.includes("/task_results/")) {
      return pending;
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ step }) });
  });

  render(
    <MemoryRouter>
      <CalibrationSessionDialog open unit="unit-1" sessionId="session-1" />
    </MemoryRouter>,
  );
  const input = await screen.findByRole("textbox", { name: "OD600 value" });
  fireEvent.change(input, { target: { value: "0.75" } });
  fireEvent.click(screen.getByRole("button", { name: "Measure standard" }));

  expect(input).toBeDisabled();
  expect(input).toHaveValue("0.75");
  expect(screen.getByRole("button", { name: "Abort" })).toBeEnabled();
  await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
    "/api/workers/unit-1/calibrations/sessions/session-1/inputs",
    expect.objectContaining({ body: JSON.stringify({ inputs: { od600_value: 0.75 }, expected_step_id: "measure_standard" }) }),
  ));
  finish({
    ok: true,
    status: 200,
    json: () => Promise.resolve(fails
      ? { status: "failed", error: "ADC failed" }
      : { status: "succeeded", result: { step: { ...step, title: "Record standard 3 of 3" } } }),
  });

  if (fails) {
    await screen.findByText("ADC failed");
    expect(input).toBeEnabled();
    expect(input).toHaveValue("0.75");
  } else {
    await screen.findByText("Record standard 3 of 3");
    expect(screen.getByRole("textbox", { name: "OD600 value" })).toBeEnabled();
  }
});

test("disables text, choice, boolean, checkbox, and table inputs together", () => {
  const props = {
    step: { fields: [
      { name: "rpm", label: "RPM", field_type: "float" },
      { name: "channel", label: "Channel", field_type: "choice", options: ["1", "2"] },
      { name: "stir", label: "Stir", field_type: "bool" },
      { name: "rows", label: "Rows", field_type: "data_table", columns: [
        { key: "run", label: "Run" }, { key: "volume", label: "Volume", editable: true },
      ] },
    ] },
    values: { rpm: 500, channel: "1", stir: "yes", rows: [{ run: 1, volume: 1.2345, include: true }] },
    onFieldChange: jest.fn(),
  };
  const { rerender } = render(<CalibrationSessionFields {...props} disabled />);
  screen.getAllByRole("textbox").forEach((input) => expect(input).toBeDisabled());
  screen.getAllByRole("combobox").forEach((input) => expect(input).toHaveAttribute("aria-disabled", "true"));
  expect(screen.getByRole("checkbox", { name: "Include Run 1" })).toBeDisabled();

  rerender(<CalibrationSessionFields {...props} disabled={false} />);
  screen.getAllByRole("textbox").forEach((input) => expect(input).toBeEnabled());
  expect(screen.getByRole("checkbox", { name: "Include Run 1" })).toBeEnabled();
});

test("submits a fractional sample count for validation without silently truncating it", async () => {
  const step = {
    step_id: "setup", step_type: "form", title: "Calibration setup",
    fields: [{ name: "sample_count", label: "Number of samples (including blank)", field_type: "int" }],
  };
  global.fetch = jest.fn((url) => Promise.resolve(url.endsWith("/inputs")
    ? { ok: false, json: () => Promise.resolve({ error: "Enter a whole number of samples." }) }
    : { ok: true, json: () => Promise.resolve({ step }) }));
  render(<MemoryRouter><CalibrationSessionDialog open unit="unit-1" sessionId="session-1" /></MemoryRouter>);
  const count = await screen.findByRole("textbox", { name: "Number of samples (including blank)" });
  fireEvent.change(count, { target: { value: "2.5" } });
  fireEvent.click(screen.getByRole("button", { name: "Continue" }));
  await screen.findByText("Enter a whole number of samples.");
  expect(count).toHaveValue("2.5");
  expect(count).toBeEnabled();
  expect(global.fetch).toHaveBeenCalledWith(
    "/api/workers/unit-1/calibrations/sessions/session-1/inputs",
    expect.objectContaining({ body: JSON.stringify({ inputs: { sample_count: 2.5 }, expected_step_id: "setup" }) }),
  );
});
