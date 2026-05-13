import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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
      "unit-1": {
        calibration_type: "od",
        created_at: "2026-05-12T12:00:00Z",
        curve_data_: { type: "poly", coefficients: [1, 2] },
        x: "voltage",
        y: "od",
        recorded_data: { x: [1, 2], y: [3, 4] },
        is_active: isActive,
      },
    },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderSingleCalibrationPage() {
  return render(
    <MemoryRouter initialEntries={["/calibrations/unit-1/od/calibration-a"]}>
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
    mockConfirm.mockResolvedValue();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od/calibration-a") {
        return Promise.resolve({ result: { "unit-1": { status: "success" } } });
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

    await screen.findByText("Calibration: calibration-a");
    await user.click(screen.getByRole("button", { name: /set active/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_calibrations/od/calibration-a",
        { fetchOptions: { method: "PATCH" } },
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Calibration set as Active");
  });

  test("shows the unit failure instead of reporting active-calibration success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od/calibration-a") {
        return Promise.resolve({ result: { "unit-1": null } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleCalibrationPage();

    await screen.findByText("Calibration: calibration-a");
    await user.click(screen.getByRole("button", { name: /set active/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Unable to set calibration active on unit-1.",
    );
    expect(screen.queryByText("Calibration set as Active")).not.toBeInTheDocument();
  });

  test("waits for the remove-active task before reporting success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/calibrations/od/calibration-a") {
        return Promise.resolve(calibrationPayload(true));
      }
      if (endpoint === "/api/workers/unit-1/active_calibrations/od") {
        return Promise.resolve({ result: { "unit-1": { status: "success" } } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleCalibrationPage();

    await screen.findByText("Calibration: calibration-a");
    await user.click(screen.getByRole("button", { name: /set inactive/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_calibrations/od",
        { fetchOptions: { method: "DELETE" } },
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Calibration is no longer Active");
  });

  test("waits for the delete task before navigating away", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockResolvedValueOnce(calibrationPayload(false));
    fetchTaskResult.mockResolvedValueOnce({ result: { "unit-1": { msg: "deleted" } } });

    renderSingleCalibrationPage();

    await screen.findByText("Calibration: calibration-a");
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
