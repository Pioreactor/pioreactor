import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utils/tasks", () => ({
  fetchTaskResult: jest.fn(),
  getSuccessfulUnitTaskResults: jest.fn((payload) => payload?.result ?? {}),
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
const { fetchTaskResult, getSuccessfulUnitTaskResults } = require("../utils/tasks");
const {
  default: Calibrations,
  UploadCalibrationDialog,
  getFailedCalibrationUploadUnits,
} = require("../Calibrations");

describe("UploadCalibrationDialog", () => {
  const uploadTask = jest.fn();
  const protocolsByUnit = {
    xr1: [{ target_device: "od90" }, { target_device: "od" }, { target_device: "plugin_sensor" }],
    xr2: [{ target_device: "od90" }, { target_device: "od" }],
  };
  beforeEach(() => {
    uploadTask.mockReset();
    getSuccessfulUnitTaskResults.mockImplementation((payload) => Object.fromEntries(
      Object.entries(payload.result).filter(([, result]) => result?.ok).map(([unit, result]) => [unit, result.value]),
    ));
    fetchTaskResult.mockImplementation((endpoint, options) => {
      if (endpoint.endsWith('/calibration_protocols')) {
        const unit = endpoint.split('/')[3];
        return Promise.resolve({ result: Object.fromEntries(
          Object.entries(unit === '$broadcast' ? protocolsByUnit : { [unit]: protocolsByUnit[unit] })
            .map(([name, protocols]) => [name, { ok: true, value: protocols }]),
        ) });
      }
      return uploadTask(endpoint, options);
    });
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

  test("queries the selected unit and preserves plugin device names", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/calibrations/xr1/od90"]}>
        <Routes>
          <Route path="/calibrations/:pioreactorUnit/:device" element={<UploadCalibrationDialog open onClose={() => {}} />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/xr1/calibration_protocols");
    expect(screen.getByRole("combobox", { name: /Device/ })).toHaveTextContent("od90");
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.getByRole("option", { name: "plugin_sensor" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "od", exact: true })).not.toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(screen.getAllByRole("combobox")[0]);
    await user.click(screen.getByRole("option", { name: "xr2" }));
    await waitFor(() => expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/xr2/calibration_protocols"));
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.queryByRole("option", { name: "plugin_sensor" })).not.toBeInTheDocument();
  });

  test("shows only shared registry devices for a broadcast upload", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><UploadCalibrationDialog open onClose={() => {}} /></MemoryRouter>);
    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/$broadcast/calibration_protocols");
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.getByRole("option", { name: "od90" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "plugin_sensor" })).not.toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "od", exact: true })).not.toBeInTheDocument();
  });

  test("blocks uploads and reports a registry query failure", async () => {
    fetchTaskResult.mockRejectedValue(new Error("Registry unavailable"));
    render(<MemoryRouter><UploadCalibrationDialog open onClose={() => {}} /></MemoryRouter>);
    expect(await screen.findByText("Registry unavailable")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /Device/ })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: "Upload calibration" })).toBeDisabled();
  });

  test("shows failed unit names when a broadcast upload has partial failures", async () => {
    const user = userEvent.setup();

    uploadTask.mockResolvedValue({
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

    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.queryByRole("option", { name: "od", exact: true })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "od90" }));
    await user.type(screen.getByLabelText("YAML description"), "calibration_name: test");
    await user.click(screen.getByRole("button", { name: "Upload calibration" }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/$broadcast/calibrations/od90",
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

    uploadTask.mockResolvedValue({
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

    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.queryByRole("option", { name: "od", exact: true })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "od90" }));
    const yamlEditor = screen.getByLabelText("YAML description");
    await user.type(yamlEditor, "calibration_name: test");
    await user.click(screen.getByRole("button", { name: "Upload calibration" }));

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

    uploadTask.mockReturnValue(uploadPromise);

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

    await waitFor(() => expect(screen.getByRole("combobox", { name: /Device/ })).not.toHaveAttribute("aria-disabled", "true"));
    await user.click(screen.getByRole("combobox", { name: /Device/ }));
    expect(screen.queryByRole("option", { name: "od", exact: true })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "od90" }));
    await user.type(screen.getByLabelText("YAML description"), "calibration_name: test");
    const uploadButton = screen.getByRole("button", { name: "Upload calibration" });
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
});

describe("calibration downloads", () => {
  beforeEach(() => {
    getSuccessfulUnitTaskResults.mockReturnValue({ xr1: {} });
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.resetAllMocks();
  });

  test("shows pending and failure feedback while downloading all calibrations", async () => {
    const user = userEvent.setup();
    let resolveDownload;
    const downloadPromise = new Promise((resolve) => {
      resolveDownload = resolve;
    });

    fetchTaskResult.mockResolvedValue({ status: "succeeded", result: {} });
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }
      if (url === "/api/workers/$broadcast/zipped_calibrations") {
        return downloadPromise;
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });
    jest.spyOn(console, "error").mockImplementation(() => {});
    jest.spyOn(console, "warn").mockImplementation(() => {});

    render(
      <MemoryRouter initialEntries={["/calibrations"]}>
        <Calibrations title="Calibrations" />
      </MemoryRouter>,
    );

    const downloadButton = await screen.findByRole("button", {
      name: "Download all calibrations",
    });
    await user.click(downloadButton);

    await waitFor(() => expect(downloadButton).toBeDisabled());

    await act(async () => {
      resolveDownload({ ok: false, status: 503 });
      await downloadPromise;
    });

    expect(
      await screen.findByText(
        "Could not download calibrations. Check that the Pioreactors are online and try again.",
      ),
    ).toBeInTheDocument();
    expect(downloadButton).toBeEnabled();
  });
});
