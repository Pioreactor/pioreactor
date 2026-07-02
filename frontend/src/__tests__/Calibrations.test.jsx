import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
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

  test("shows upload success and clears the YAML after a successful upload", async () => {
    const user = userEvent.setup();

    fetchTaskResult.mockResolvedValue({
      result: {
        xr1: {
          msg: "Calibration created successfully.",
          path: "/tmp/xr1.yaml",
        },
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
    const yamlEditor = screen.getByLabelText("YAML description");
    await user.type(yamlEditor, "calibration_name: test");
    await user.click(screen.getByRole("button", { name: "Upload" }));

    expect(
      await screen.findByText(/Calibration sent to Pioreactor\(s\)/),
    ).toBeInTheDocument();
    expect(yamlEditor).toHaveValue("");
    expect(screen.queryByText(/Calibration upload failed/)).not.toBeInTheDocument();
  });

  test("keeps upload pending until the calibration task resolves", async () => {
    const user = userEvent.setup();
    let resolveUpload;
    const uploadPromise = new Promise((resolve) => {
      resolveUpload = resolve;
    });

    fetchTaskResult.mockReturnValue(uploadPromise);

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
    const uploadButton = screen.getByRole("button", { name: "Upload" });
    await user.click(uploadButton);

    await waitFor(() => expect(uploadButton).toBeDisabled());

    await act(async () => {
      resolveUpload({
        result: {
          xr1: {
            msg: "Calibration created successfully.",
            path: "/tmp/xr1.yaml",
          },
        },
      });
      await uploadPromise;
    });

    expect(await screen.findByText(/Calibration sent to Pioreactor\(s\)/)).toBeInTheDocument();
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
