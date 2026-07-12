import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const CameraPanel = require("../components/CameraPanel").default;

describe("CameraPanel", () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test("shows latest capture time since the experiment began with the timestamp in a tooltip", () => {
    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          experimentStartTime="2026-06-11T10:30:00Z"
          initialStatus={{
            available: true,
            latest_still: {
              image_id: "image-1",
              captured_at: "2026-06-11T12:00:00Z",
              experiment: "experiment-a",
            },
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText("1.5 h")).toHaveAttribute(
      "aria-label",
      dayjs("2026-06-11T12:00:00Z").format("YYYY-MM-DD HH:mm:ss"),
    );
  });

  test("loads status and the latest still from the selected experiment", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          available: true,
          latest_still: {
            image_id: "image-1",
            captured_at: "2026-06-11T12:00:00Z",
            experiment: "experiment-a",
          },
        }),
      }),
    );

    render(
      <MemoryRouter>
        <CameraPanel unit="unit-1" experiment="experiment-a" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workers/unit-1/camera/experiments/experiment-a/status",
        expect.objectContaining({ signal: expect.anything() }),
      );
    });
    expect(await screen.findByAltText("Latest camera still for unit-1")).toHaveAttribute(
      "src",
      "/api/workers/unit-1/camera/experiments/experiment-a/stills/image-1.jpg",
    );
  });
});
