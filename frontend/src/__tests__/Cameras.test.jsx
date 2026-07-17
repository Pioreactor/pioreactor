import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: {
      experiment: "experiment-a",
      created_at: "2026-06-11T10:30:00Z",
    },
  }),
}));

const { MemoryRouter } = require("react-router");
const Cameras = require("../Cameras").default;

describe("Cameras", () => {
  beforeEach(() => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          cameras: {
            "unit-1": {
              ok: true,
              value: {
                available: true,
                snapshot_interval_minutes: 0,
                latest_still: {
                  image_id: "image-1",
                  captured_at: "2026-06-11T12:00:00Z",
                  experiment: "experiment-a",
                },
              },
            },
          },
        }),
      }),
    );
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("shows camera capture time since the experiment began", async () => {
    render(
      <MemoryRouter>
        <Cameras title="Cameras" />
      </MemoryRouter>,
    );

    expect(await screen.findByText("1.5 h")).toBeInTheDocument();
  });

  test("keeps stored camera snapshots visible when camera hardware is unavailable", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          cameras: {
            "unit-1": {
              ok: true,
              value: {
                available: false,
                snapshot_interval_minutes: 0,
                latest_still: {
                  image_id: "image-1",
                  captured_at: "2026-06-11T12:00:00Z",
                  experiment: "experiment-a",
                },
              },
            },
          },
        }),
      }),
    );

    render(
      <MemoryRouter>
        <Cameras title="Cameras" />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Camera unavailable")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Latest camera snapshot for unit-1" })).toHaveAttribute(
      "src",
      "/api/workers/unit-1/camera/experiments/experiment-a/stills/image-1.jpg",
    );
    expect(screen.getByRole("link", { name: "View snapshot history" })).toHaveAttribute(
      "href",
      "/cameras/unit-1",
    );
    expect(screen.getByRole("link", { name: "Open image" })).toHaveAttribute(
      "href",
      "/api/workers/unit-1/camera/experiments/experiment-a/stills/image-1.jpg",
    );
  });
});
