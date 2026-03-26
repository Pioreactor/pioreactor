import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utils/tasks", () => ({
  fetchTaskResult: jest.fn(),
}));

const { MemoryRouter, Route, Routes } = require("react-router");
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

describe("Protocols", () => {
  beforeEach(() => {
    window.sessionStorage.clear();

    fetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": [
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
});
