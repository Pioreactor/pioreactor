import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const StirringCalibrationBatchDialog = require("../components/StirringCalibrationBatchDialog").default;

describe("StirringCalibrationBatchDialog", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test("closes from the title-bar close button before a batch starts", () => {
    const onClose = jest.fn();

    render(
      <MemoryRouter>
        <StirringCalibrationBatchDialog
          open
          protocol={{
            title: "DC-based stirring calibration",
            protocol_name: "dc_based",
            target_device: "stirring",
          }}
          units={["unit-1"]}
          onClose={onClose}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getAllByRole("button", { name: "Close" })[0]);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("starts a stirring batch and shows unit results", async () => {
    global.fetch = jest.fn((url, options) => {
      if (url === "/api/workers/unit-1/calibrations/sessions") {
        expect(options.method).toBe("POST");
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              session: {
                session_id: "session-1",
              },
            }),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/inputs") {
        expect(options.method).toBe("POST");
        return Promise.resolve({
          ok: true,
          status: 202,
          json: () => Promise.resolve({ task_id: "task-1" }),
        });
      }

      if (url === "/api/workers/unit-1/task_results/task-1") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              status: "succeeded",
              result: {
                step: {
                  result: {
                    calibrations: [
                      {
                        device: "stirring",
                        calibration_name: "stirring-calibration-unit-1",
                      },
                    ],
                  },
                },
              },
            }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter>
        <StirringCalibrationBatchDialog
          open
          protocol={{
            title: "DC-based stirring calibration",
            protocol_name: "dc_based",
            target_device: "stirring",
          }}
          units={["unit-1"]}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Continue"));

    expect(await screen.findByText("completed")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "stirring-calibration-unit-1" })).toHaveAttribute(
      "href",
      "/calibrations/unit-1/stirring/stirring-calibration-unit-1",
    );
  });

  test("allows deselecting Pioreactors before starting the batch", async () => {
    global.fetch = jest.fn((url, options) => {
      if (url === "/api/workers/unit-1/calibrations/sessions") {
        expect(options.method).toBe("POST");
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              session: {
                session_id: "session-1",
              },
            }),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/inputs") {
        expect(options.method).toBe("POST");
        return Promise.resolve({
          ok: true,
          status: 202,
          json: () => Promise.resolve({ task_id: "task-1" }),
        });
      }

      if (url === "/api/workers/unit-1/task_results/task-1") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              status: "succeeded",
              result: {
                step: {
                  result: {
                    calibrations: [
                      {
                        device: "stirring",
                        calibration_name: "stirring-calibration-unit-1",
                      },
                    ],
                  },
                },
              },
            }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter>
        <StirringCalibrationBatchDialog
          open
          protocol={{
            title: "DC-based stirring calibration",
            protocol_name: "dc_based",
            target_device: "stirring",
          }}
          units={["unit-1", "unit-2"]}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByLabelText("unit-2"));
    fireEvent.click(screen.getByText("Continue"));

    expect(await screen.findByText("1 Pioreactors selected")).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalledWith(
      "/api/workers/unit-2/calibrations/sessions",
      expect.anything(),
    );
    expect(await screen.findByText("completed")).toBeInTheDocument();
  });

  test("saves each unit's review step with every reading kept", async () => {
    const recordedRows = [
      { dc: 20, rpm: 300, include: true },
      { dc: 30, rpm: 450, include: true },
    ];
    const stepsByTask = {
      "task-1": { step_id: "run_calibration", step_type: "action", fields: [] },
      "task-2": {
        step_id: "review_data",
        step_type: "form",
        fields: [
          {
            name: "recorded_data",
            field_type: "data_table",
            columns: [
              { key: "dc", label: "Duty cycle (%)", editable: false },
              { key: "rpm", label: "RPM", editable: false },
            ],
            default: recordedRows,
          },
        ],
      },
      "task-3": {
        result: {
          calibrations: [{ device: "stirring", calibration_name: "stirring-calibration-unit-1" }],
        },
      },
    };
    let advanceCount = 0;

    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ session: { session_id: "session-1" } }),
        });
      }
      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/inputs") {
        advanceCount += 1;
        return Promise.resolve({
          ok: true,
          status: 202,
          json: () => Promise.resolve({ task_id: `task-${advanceCount}` }),
        });
      }
      const taskMatch = url.match(/^\/api\/workers\/unit-1\/task_results\/(task-\d)$/);
      if (taskMatch) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ status: "succeeded", result: { step: stepsByTask[taskMatch[1]] } }),
        });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter>
        <StirringCalibrationBatchDialog
          open
          protocol={{
            title: "DC-based stirring calibration",
            protocol_name: "dc_based",
            target_device: "stirring",
          }}
          units={["unit-1"]}
          onClose={() => {}}
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByText("Continue"));

    expect(await screen.findByRole("link", { name: "stirring-calibration-unit-1" })).toBeInTheDocument();
    expect(advanceCount).toBe(3);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions/session-1/inputs",
      expect.objectContaining({ body: JSON.stringify({ inputs: { recorded_data: recordedRows } }) }),
    );
  });
});
