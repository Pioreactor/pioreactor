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

  test("starts a stirring batch and shows unit results", async () => {
    global.fetch = jest.fn((url, options) => {
      if (url === "/api/calibration_batches/stirring") {
        expect(options.method).toBe("POST");
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              batch: {
                batch_id: "batch-1",
                status: "complete",
                units: {
                  "unit-1": {
                    status: "completed",
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
          protocol={{ title: "DC-based stirring calibration" }}
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
});
