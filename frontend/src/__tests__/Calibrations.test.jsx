import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utils/tasks", () => ({
  fetchTaskResult: jest.fn(),
}));

jest.mock("react-simple-code-editor", () => ({
  __esModule: true,
  default: ({ value, onValueChange }) => (
    <textarea
      aria-label="YAML description"
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
    />
  ),
}));

const { MemoryRouter, Route, Routes } = require("react-router");
const { fetchTaskResult } = require("../utils/tasks");
const {
  UploadCalibrationDialog,
  buildCalibrationUploadFailureMessage,
  getFailedCalibrationUploadUnits,
} = require("../Calibrations");

describe("UploadCalibrationDialog", () => {
  beforeEach(() => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              { pioreactor_unit: "xr1" },
              { pioreactor_unit: "xr2" },
            ]),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("shows failed unit names when a broadcast upload has partial failures", async () => {
    const user = userEvent.setup();

    fetchTaskResult.mockResolvedValue({
      result: {
        xr1: null,
        xr2: {
          msg: "Calibration created successfully.",
          path: "/tmp/xr2.yaml",
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/calibrations"]}>
        <Routes>
          <Route
            path="*"
            element={<UploadCalibrationDialog open={true} onClose={() => {}} />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/workers"));

    await user.type(screen.getByPlaceholderText("e.g. od, media_pump"), "od");
    await user.type(screen.getByLabelText("YAML description"), "calibration_name: test");
    await user.click(screen.getByRole("button", { name: "Upload" }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/$broadcast/calibrations/od",
        expect.objectContaining({
          fetchOptions: expect.objectContaining({
            method: "POST",
          }),
        }),
      ),
    );

    expect(
      await screen.findByText("Calibration upload failed for unit: xr1."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Calibration sent to Pioreactor/)).not.toBeInTheDocument();
  });
});

describe("calibration upload helpers", () => {
  test("collects failed units from task results", () => {
    expect(
      getFailedCalibrationUploadUnits({
        result: {
          xr2: { msg: "ok" },
          xr1: null,
          xr3: null,
        },
      }),
    ).toEqual(["xr1", "xr3"]);
  });

  test("formats failed unit names into a single message", () => {
    expect(buildCalibrationUploadFailureMessage(["xr1"])).toBe(
      "Calibration upload failed for unit: xr1.",
    );
    expect(buildCalibrationUploadFailureMessage(["xr1", "xr3"])).toBe(
      "Calibration upload failed for units: xr1, xr3.",
    );
  });
});
