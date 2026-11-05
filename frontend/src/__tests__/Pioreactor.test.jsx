import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockSelectExperiment = jest.fn();
const mockCameraPanel = jest.fn();

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: { experiment: "exp1", started_at: "2026-01-01T00:00:00Z" },
    selectExperiment: mockSelectExperiment,
  }),
}));

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: null,
    subscribeToTopic: jest.fn(),
    unsubscribeFromTopic: jest.fn(),
  }),
}));

jest.mock("../utils/jobs", () => ({
  ...jest.requireActual("../utils/jobs"),
  getWorkerJobDescriptors: () => Promise.resolve([]),
  getWorkerSettingsDescriptors: () => Promise.resolve([]),
}));

jest.mock("../utils/config", () => ({
  ...jest.requireActual("../utils/config"),
  getRelabelMap: jest.fn(),
}));

jest.mock("../hooks/useExperimentChartPreferences", () => () => ({ descriptors: [], selectedChartKeys: [], error: null }));
jest.mock("../components/ChartPreferencesControl", () => () => null);
jest.mock("../components/LogTableByUnit", () => () => <div>log table</div>);
jest.mock("../components/BioreactorDiagramPanel", () => () => null);
jest.mock("../components/CameraPanel", () => (props) => {
  mockCameraPanel(props);
  return null;
});

const { MemoryRouter, Route, Routes } = require("react-router");
const { default: Pioreactor } = require("../Pioreactor");

function jsonResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  });
}

function mockApi({ assignment, worker = { pioreactor_unit: "unit1", is_active: 1 } }) {
  let currentAssignment = assignment;
  global.fetch = jest.fn((url, options = {}) => {
    if (url === "/api/workers/unit1") {
      return worker
        ? jsonResponse({ ...worker, experiment: currentAssignment })
        : jsonResponse({ error: "Worker `unit1` not found." }, 404);
    }
    if (url === "/api/workers/unit1/model") {
      return jsonResponse({ model_name: "pioreactor_40ml", display_name: "Pioreactor 40mL" });
    }
    if (url === "/api/config/units/unit1") {
      return jsonResponse({ configs: { unit1: {} } });
    }
    if (url === "/api/experiments/exp1/workers" && options.method === "PUT") {
      currentAssignment = "exp1";
      return jsonResponse({});
    }
    throw new Error(`Unexpected fetch call: ${url}`);
  });
}

function renderPage() {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter initialEntries={["/pioreactors/unit1"]}>
        <Routes>
          <Route path="/pioreactors/:pioreactorUnit" element={<Pioreactor title="Pioreactor" />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

function lastCameraPanelProps() {
  return mockCameraPanel.mock.calls[mockCameraPanel.mock.calls.length - 1][0];
}

describe("Pioreactor page for a worker outside the selected experiment", () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test("shows past data read-only when the worker moved to another experiment", async () => {
    mockApi({ assignment: "exp2" });
    renderPage();

    expect(await screen.findByText(/now assigned to experiment/)).toBeInTheDocument();
    expect(screen.getByText("log table")).toBeInTheDocument();
    expect(lastCameraPanelProps()).toEqual(expect.objectContaining({ experiment: "exp1", controlsDisabled: true }));
    expect(screen.getByRole("button", { name: "Stop" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Switch experiment" }));
    expect(mockSelectExperiment).toHaveBeenCalledWith("exp2");
  });

  test("shows past data instead of an error when the worker is unassigned, and can assign it", async () => {
    mockApi({ assignment: null });
    renderPage();

    expect(await screen.findByText(/isn't assigned to an experiment/)).toBeInTheDocument();
    expect(screen.getByText("None")).toBeInTheDocument();
    expect(screen.getByText("log table")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Assign to this experiment" }));

    await waitFor(() => expect(screen.queryByText(/isn't assigned to an experiment/)).not.toBeInTheDocument());
    expect(global.fetch).toHaveBeenCalledWith("/api/experiments/exp1/workers", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ pioreactor_unit: "unit1" }),
    }));
    expect(lastCameraPanelProps().controlsDisabled).toBe(false);
  });

  test("still reports an unknown worker as an error", async () => {
    mockApi({ assignment: null, worker: null });
    renderPage();

    expect(await screen.findByText("Worker `unit1` not found.")).toBeInTheDocument();
  });

  test("shows no notice when the worker is in the selected experiment", async () => {
    mockApi({ assignment: "exp1" });
    renderPage();

    await waitFor(() => expect(lastCameraPanelProps().controlsDisabled).toBe(false));
    expect(screen.queryByText(/Showing its data from/)).not.toBeInTheDocument();
  });
});
