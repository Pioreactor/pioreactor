import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utils/tasks", () => ({
  ...jest.requireActual("../utils/tasks"),
  fetchTaskResult: jest.fn(),
}));

const { MemoryRouter, Route, Routes, useNavigate } = require("react-router");
const Protocols = require("../Protocols").default;
const { fetchTaskResult } = require("../utils/tasks");

const renderProtocols = (initialEntry = "/protocols") =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/protocols/:pioreactorUnit?/:device?" element={<Protocols title="Pioreactor ~ Protocols" />} />
      </Routes>
    </MemoryRouter>,
  );

function ProtocolsWithUnitSwitcher() {
  const navigate = useNavigate();

  return (
    <>
      <button type="button" onClick={() => navigate("/protocols/unit-1/stirring")}>
        Switch to unit-1
      </button>
      <button type="button" onClick={() => navigate("/protocols/unit-2/stirring")}>
        Switch to unit-2
      </button>
      <Routes>
        <Route path="/protocols/:pioreactorUnit?/:device?" element={<Protocols title="Pioreactor ~ Protocols" />} />
      </Routes>
    </>
  );
}

const renderProtocolsWithUnitSwitcher = (initialEntry = "/protocols/unit-1/stirring") =>
  render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <ProtocolsWithUnitSwitcher />
    </MemoryRouter>,
  );

function createDeferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });

  return { promise, resolve };
}

function successfulProtocolTask(unit, title) {
  return {
    result: {
      [unit]: {
        ok: true,
        value: [
          {
            id: "stirring_dc_based",
            target_device: "stirring",
            protocol_name: "dc_based",
            title,
            description: "Maps duty cycle to RPM.",
            requirements: ["Vial"],
          },
        ],
      },
    },
  };
}

describe("Protocols", () => {
  beforeEach(() => {
    window.sessionStorage.clear();

    fetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": {
          ok: true,
          value: [
            {
              id: "stirring_dc_based",
              target_device: "stirring",
              protocol_name: "dc_based",
              title: "DC-based stirring calibration",
              description: "Maps duty cycle to RPM.",
              requirements: ["Vial"],
            },
            {
              id: "od_standards",
              target_device: "od",
              protocol_name: "standards",
              title: "OD standards calibration",
              description: "Builds OD standards.",
              requirements: ["Standards"],
            },
          ],
        },
      },
    });

    global.fetch = jest.fn((url) => {
      if (url === "/api/workers") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "unit-1" }]),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              session: {
                session_id: "session-1",
                status: "in_progress",
              },
            }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
    window.sessionStorage.clear();
  });

  test("restores a resumable calibration session from sessionStorage", async () => {
    window.sessionStorage.setItem(
      "activeCalibrationSession",
      JSON.stringify({
        sessionId: "session-1",
        unit: "unit-1",
        protocolId: "stirring_dc_based",
        targetDevice: "stirring",
      }),
    );

    renderProtocols();

    await screen.findByText("Resume protocol");

    expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/unit-1/calibration_protocols");
    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit-1/calibrations/sessions/session-1");
  });

  test("falls back to the first available device when the route device is invalid", async () => {
    renderProtocols("/protocols/unit-1/not-a-device");

    expect(await screen.findByText("DC-based stirring calibration")).toBeInTheDocument();
    expect(screen.queryByText("OD standards calibration")).toBeNull();
  });

  test("prefers the route device when it matches an available protocol device", async () => {
    renderProtocols("/protocols/unit-1/od");

    expect(await screen.findByText("OD standards calibration")).toBeInTheDocument();
    expect(screen.queryByText("DC-based stirring calibration")).toBeNull();
  });

  test("shows the stirring batch action for all pioreactors", async () => {
    fetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": {
          ok: true,
          value: [
            {
              id: "stirring_dc_based",
              target_device: "stirring",
              protocol_name: "dc_based",
              title: "DC-based stirring calibration",
              description: "Maps duty cycle to RPM.",
              requirements: ["Vial"],
            },
          ],
        },
        "unit-2": {
          ok: true,
          value: [
            {
              id: "stirring_dc_based",
              target_device: "stirring",
              protocol_name: "dc_based",
              title: "DC-based stirring calibration",
              description: "Maps duty cycle to RPM.",
              requirements: ["Vial"],
            },
          ],
        },
      },
    });

    global.fetch = jest.fn((url) => {
      if (url === "/api/workers") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "unit-1" }, { pioreactor_unit: "unit-2" }]),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderProtocols("/protocols/$broadcast/stirring");

    expect(await screen.findByText("Run on all Pioreactors")).toBeInTheDocument();
    expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/$broadcast/calibration_protocols");
  });

  test("shows an offline-worker message when the selected worker is unreachable", async () => {
    fetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": {
          ok: false,
          error: {
            message: "Could not reach this worker.",
          },
        },
      },
    });

    renderProtocols("/protocols/unit-1");

    expect(await screen.findByText("Could not reach this worker.")).toBeInTheDocument();
  });

  test("clears old cards and ignores stale protocol responses after rapid unit switches", async () => {
    const initialUnitOne = createDeferred();
    const unitTwo = createDeferred();
    const returningUnitOne = createDeferred();
    const finalUnitTwo = createDeferred();
    const requests = {
      "/api/workers/unit-1/calibration_protocols": [initialUnitOne, returningUnitOne],
      "/api/workers/unit-2/calibration_protocols": [unitTwo, finalUnitTwo],
    };

    fetchTaskResult.mockImplementation((url) => {
      const request = requests[url]?.shift();
      if (!request) {
        throw new Error(`Unexpected protocol request: ${url}`);
      }
      return request.promise;
    });
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "unit-1" }, { pioreactor_unit: "unit-2" }]),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderProtocolsWithUnitSwitcher();

    await waitFor(() => {
      expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/unit-1/calibration_protocols");
    });
    await act(async () => {
      initialUnitOne.resolve(successfulProtocolTask("unit-1", "Unit 1 protocol"));
    });
    expect(await screen.findByText("Unit 1 protocol")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Switch to unit-2" }));
    await waitFor(() => {
      expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/unit-2/calibration_protocols");
      expect(screen.queryByText("Unit 1 protocol")).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: "Switch to unit-1" }));
    fireEvent.click(screen.getByRole("button", { name: "Switch to unit-2" }));
    await waitFor(() => {
      expect(fetchTaskResult).toHaveBeenCalledTimes(4);
    });

    await act(async () => {
      finalUnitTwo.resolve(successfulProtocolTask("unit-2", "Unit 2 protocol"));
    });
    expect(await screen.findByText("Unit 2 protocol")).toBeInTheDocument();

    await act(async () => {
      returningUnitOne.resolve(successfulProtocolTask("unit-1", "Stale unit 1 protocol"));
    });
    expect(screen.getByText("Unit 2 protocol")).toBeInTheDocument();
    expect(screen.queryByText("Stale unit 1 protocol")).toBeNull();
  });
});
