import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../utilities", () => ({
  fetchTaskResult: jest.fn(),
}));

const { MemoryRouter } = require("react-router");
const Protocols = require("../Protocols").default;
const { fetchTaskResult } = require("../utilities");

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

    render(
      <MemoryRouter>
        <Protocols title="Pioreactor ~ Protocols" />
      </MemoryRouter>,
    );

    await screen.findByText("Resume protocol");

    expect(fetchTaskResult).toHaveBeenCalledWith("/api/workers/unit-1/calibration_protocols");
    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit-1/calibrations/sessions/session-1");
  });
});
