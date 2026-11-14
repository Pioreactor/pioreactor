import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockConfirm = jest.fn();

jest.mock("../utils/tasks", () => {
  const actual = jest.requireActual("../utils/tasks");
  return {
    ...actual,
    fetchTaskResult: jest.fn(),
  };
});

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => mockConfirm,
}));

jest.mock("../components/CalibrationChart", () => () => <div data-testid="calibration-chart" />);
jest.mock("../components/Snackbar", () => ({ open, message }) =>
  open ? <div role="status">{message}</div> : null,
);
jest.mock("../components/DisplaySourceCode", () => ({ sourceCode }) => <pre>{sourceCode}</pre>);

const { MemoryRouter, Route, Routes, useLocation } = require("react-router");
const { fetchTaskResult } = require("../utils/tasks");
const SingleCalibrationPage = require("../SingleCalibrationPage").default;

function calibrationPayload(isActive = false) {
  return {
    result: {
      "unit-1": fanoutSuccess({
        calibration_type: "od",
        created_at: "2026-05-12T12:00:00Z",
        curve_data_: { type: "poly", coefficients: [1, 2] },
        x: "voltage",
        y: "od",
        recorded_data: { x: [1, 2], y: [3, 4] },
        is_active: isActive,
      }),
    },
  };
}

function fanoutSuccess(value = {}) {
  return { ok: true, unit: "unit-1", value };
}

function fanoutFailure(message = "Worker rejected this request.") {
  return {
    ok: false,
    unit: "unit-1",
    error: { kind: "http_error", message },
    status_code: 500,
    retryable: true,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderSingleCalibrationPage(path = "/calibrations/unit-1/od/calibration-a") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route
          path="/calibrations/:pioreactorUnit/:device/:calibrationName"
          element={<SingleCalibrationPage title="Calibration" />}
        />
        <Route path="/calibrations/:pioreactorUnit/:device" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SingleCalibrationPage task-backed mutations", () => {
  beforeEach(() => {
    mockConfirm.mockResolvedValue({ confirmed: true, reason: "confirm" });
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od/calibration-a") {
        return Promise.resolve({ result: { "unit-1": fanoutSuccess() } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("waits for the active-calibration task before reporting success", async () => {
    const user = userEvent.setup();
    renderSingleCalibrationPage();

    await screen.findByRole("heading", { name: "Calibration: calibration-a" });
    await user.click(screen.getByRole("button", { name: /set active/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_calibrations/od/calibration-a",
        { fetchOptions: { method: "PATCH" } },
      ),
    );
    expect(await screen.findByRole("status")).toBeVisible();
  });

  test("shows the unit failure instead of reporting active-calibration success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od/calibration-a") {
        return Promise.resolve({ result: { "unit-1": fanoutFailure() } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleCalibrationPage();

    await screen.findByRole("heading", { name: "Calibration: calibration-a" });
    await user.click(screen.getByRole("button", { name: /set active/i }));

    expect(await screen.findByRole("status")).toHaveTextContent("Worker rejected this request.");
  });

  test("waits for the remove-active task before reporting success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(true));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od") {
        return Promise.resolve({ result: { "unit-1": fanoutSuccess() } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleCalibrationPage();

    await user.click(await screen.findByRole("button", { name: /set inactive/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_calibrations/od",
        { fetchOptions: { method: "DELETE" } },
      ),
    );
    expect(await screen.findByRole("status")).toBeVisible();
  });


  test.each(["cancel", "natural", "unmount"])("does not delete on %s", async (reason) => {
    const user = userEvent.setup();
    mockConfirm.mockResolvedValue({ confirmed: false, reason });
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload(false));
    renderSingleCalibrationPage();
    await screen.findByRole("heading", { name: "Calibration: calibration-a" });
    fetchTaskResult.mockClear();

    await user.click(screen.getByRole("button", { name: /delete/i }));

    expect(fetchTaskResult).not.toHaveBeenCalled();
    expect(screen.getByRole("heading", { name: "Calibration: calibration-a" })).toBeInTheDocument();
  });

  test("waits for the delete task before navigating away", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload(false));
    fetchTaskResult.mockResolvedValueOnce({ result: { "unit-1": fanoutSuccess({ msg: "deleted" }) } });

    renderSingleCalibrationPage();

    await screen.findByRole("heading", { name: "Calibration: calibration-a" });
    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/calibrations/od/calibration-a",
        { fetchOptions: { method: "DELETE" } },
      ),
    );
    expect(await screen.findByTestId("location")).toHaveTextContent("/calibrations/unit-1/od");
  });
});

describe("SingleCalibrationPage calibration names", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test("loads a calibration whose name has URL-reserved characters", async () => {
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/OD600%20%232%3F%25") {
        return Promise.resolve(calibrationPayload(false));
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleCalibrationPage(`/calibrations/unit-1/od/${encodeURIComponent("OD600 #2?%")}`);

    expect(await screen.findByRole("heading", { name: "Calibration: OD600 #2?%" })).toBeVisible();
    expect(screen.queryByText("Unable to find calibration data.")).not.toBeInTheDocument();
  });
});

describe("SingleCalibrationPage voltage display", () => {
  afterEach(() => jest.resetAllMocks());

  test.each(["x", "y"])("formats the %s voltage column while preserving raw calibration data", async (voltageAxis) => {
    const payload = calibrationPayload();
    const calibration = payload.result["unit-1"].value;
    calibration.x = voltageAxis === "x" ? "Voltage" : "OD600";
    calibration.y = voltageAxis === "y" ? "Voltage" : "OD600";
    const voltages = [0.123456789, 0.00000123456789, 0, null];
    calibration.recorded_data = {
      x: voltageAxis === "x" ? voltages : [0, 1, 2, 3],
      y: voltageAxis === "y" ? voltages : [0, 1, 2, 3],
    };
    fetchTaskResult.mockResolvedValue(payload);

    renderSingleCalibrationPage();

    expect(await screen.findByRole("columnheader", { name: "Voltage (V)" })).toBeVisible();
    expect(screen.getByText("0.123")).toBeVisible();
    expect(screen.getByText("1.23e-6")).toBeVisible();
    const table = screen.getByRole("columnheader", { name: "Voltage (V)" }).closest("table");
    expect(within(table).getAllByText("0").length).toBeGreaterThan(0);
    expect(screen.getByText("—")).toBeVisible();
    expect(screen.getByText("Calibration curve")).toBeVisible();
    expect(calibration.recorded_data[voltageAxis]).toEqual(voltages);
  });

  test.each([
    ["Duration", "Volume", 1.23456789, 0.123456789, "1.235", "0.123"],
    ["DC %", "RPM", 32.123456789, 502.123456789, "32.12", "502.1"],
    ["Reference pH", "Measured pH", 2, 2.0123456789, "2", "2.012"],
  ])("formats %s and %s recorded measurements", async (x, y, xValue, yValue, xDisplay, yDisplay) => {
    const payload = calibrationPayload();
    const calibration = payload.result["unit-1"].value;
    calibration.x = x;
    calibration.y = y;
    calibration.recorded_data = { x: [xValue], y: [yValue] };
    fetchTaskResult.mockResolvedValue(payload);

    renderSingleCalibrationPage();

    const table = (await screen.findByRole("columnheader", { name: x })).closest("table");
    expect(within(table).getByText(xDisplay)).toBeVisible();
    expect(within(table).getByText(yDisplay)).toBeVisible();
    expect(calibration.recorded_data).toEqual({ x: [xValue], y: [yValue] });
  });
});

describe("saved measurement inclusion", () => {
  afterEach(() => jest.resetAllMocks());

  test("waits for persistence, sends only the mask, and can restore an excluded row", async () => {
    let complete;
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload());
    fetchTaskResult.mockImplementationOnce(() => new Promise((resolve) => { complete = resolve; }));
    const user = userEvent.setup();
    renderSingleCalibrationPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const checkbox = await screen.findByRole("checkbox", { name: "Include measurement 2" });
    expect(checkbox).toBeChecked();
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(checkbox).toBeDisabled();
    expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
    expect(fetchTaskResult.mock.calls[1][1].fetchOptions).toEqual({
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ included: [true, false] }),
    });
    const saved = calibrationPayload();
    saved.result["unit-1"].value.included = [true, false];
    complete(saved);
    await screen.findByText("Calibration recalculated and saved.");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("columnheader", { name: "Status" })).not.toBeInTheDocument();
    expect(screen.queryByText("Excluded")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const restoredCheckbox = await screen.findByRole("checkbox", { name: "Include measurement 2" });
    expect(restoredCheckbox).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload());
    await user.click(restoredCheckbox);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("Excluded")).not.toBeInTheDocument();
  });

  test("retains draft after failure and Cancel restores the saved mask", async () => {
    const saved = calibrationPayload();
    saved.result["unit-1"].value.included = [true, false];
    fetchTaskResult.mockResolvedValueOnce(saved).mockRejectedValueOnce(new Error("Include more measurements."));
    const user = userEvent.setup();
    renderSingleCalibrationPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const checkbox = await screen.findByRole("checkbox", { name: "Include measurement 2" });
    expect(checkbox).not.toBeChecked();
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    expect(checkbox).toBeChecked();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Edit" }));
    expect(await screen.findByRole("checkbox", { name: "Include measurement 2" })).not.toBeChecked();
  });
});

describe("editing recorded measurement values", () => {
  afterEach(() => jest.resetAllMocks());

  test("edits both axes, preserves full precision, and submits values with the mask", async () => {
    const payload = calibrationPayload();
    payload.result["unit-1"].value.recorded_data.y = [3.1234567890123, 4];
    fetchTaskResult.mockResolvedValueOnce(payload).mockRejectedValueOnce(new Error("Cannot fit these values."));
    const user = userEvent.setup();
    renderSingleCalibrationPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    expect(screen.getAllByRole("textbox")).toHaveLength(4);
    const first = screen.getByRole("textbox", { name: "od for measurement 1" });
    await user.click(first);
    expect(first).toHaveValue("3.1234567890123");
    const second = screen.getByRole("textbox", { name: "od for measurement 2" });
    await user.clear(second);
    await user.type(second, "4.9876543210123");
    const xField = screen.getByRole("textbox", { name: "voltage for measurement 1" });
    await user.clear(xField);
    await user.type(xField, "0.9876543210123");
    await user.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByText("Cannot fit these values.");
    expect(JSON.parse(fetchTaskResult.mock.calls[1][1].fetchOptions.body)).toEqual({
      included: [true, true], x_values: [0.9876543210123, 2], y_values: [3.1234567890123, 4.9876543210123],
    });
    await user.click(second);
    expect(second).toHaveValue("4.9876543210123");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Edit" }));
    const reopened = screen.getByRole("textbox", { name: "od for measurement 2" });
    await user.click(reopened);
    expect(reopened).toHaveValue("4");
    const reopenedX = screen.getByRole("textbox", { name: "voltage for measurement 1" });
    await user.click(reopenedX);
    expect(reopenedX).toHaveValue("1");
  });

  test("rejects empty and nonfinite values before submitting", async () => {
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload());
    const user = userEvent.setup();
    renderSingleCalibrationPage();
    await user.click(await screen.findByRole("button", { name: "Edit" }));
    const field = screen.getByRole("textbox", { name: "od for measurement 1" });
    await user.clear(field);
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    await user.type(field, "Infinity");
    expect(screen.getByText("Enter a number")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(fetchTaskResult).toHaveBeenCalledTimes(1);
  });
});
