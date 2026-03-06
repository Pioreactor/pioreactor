import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const CalibrationSessionDialog = require("../components/CalibrationSessionDialog").default;

describe("CalibrationSessionDialog", () => {
  beforeEach(() => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions") {
        throw new Error("Dialog should not start a new session when a sessionId prop is present.");
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
              step: {
                step_id: "run_calibration",
                step_type: "action",
                title: "Record calibration",
                body: "Run the hardware action.",
                fields: [],
                metadata: {},
              },
            }),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/abort") {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ error: "Cleanup failed: stirring is still running." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("keeps the dialog open and surfaces server abort errors", async () => {
    const onAbortSuccess = jest.fn();
    const onAbortFailure = jest.fn();
    const onClose = jest.fn();

    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Test protocol", protocol_name: "dummy", target_device: "device" }}
          unit="unit-1"
          sessionId="session-1"
          onAbortSuccess={onAbortSuccess}
          onAbortFailure={onAbortFailure}
          onClose={onClose}
        />
      </MemoryRouter>,
    );

    await screen.findByText("Record calibration");

    fireEvent.click(screen.getByText("Abort"));

    await screen.findByText("Cleanup failed: stirring is still running.");

    expect(onAbortSuccess).not.toHaveBeenCalled();
    expect(onAbortFailure).toHaveBeenCalledWith("Cleanup failed: stirring is still running.");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Record calibration")).toBeTruthy();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions/session-1/abort",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("loads the existing session step instead of starting over when resumed", async () => {
    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Test protocol", protocol_name: "dummy", target_device: "device" }}
          unit="unit-1"
          sessionId="session-1"
        />
      </MemoryRouter>,
    );

    await screen.findByText("Record calibration");

    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit-1/calibrations/sessions/session-1");
    expect(global.fetch).not.toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions",
      expect.anything(),
    );
  });
});
