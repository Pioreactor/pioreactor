import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: null,
    subscribeToTopic: jest.fn(),
    unsubscribeFromTopic: jest.fn(),
  }),
}));

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
                detection_status: "detected",
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
    jest.useRealTimers();
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

  test("surfaces camera-list failures and recovers on the scheduled refresh", async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn()
      .mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ error: "Timed out fetching camera statuses." }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ cameras: {} }),
      });

    render(
      <MemoryRouter>
        <Cameras title="Cameras" />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Timed out fetching camera statuses/)).toBeInTheDocument();
    expect(screen.queryByText("No assigned Pioreactors were found.")).not.toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(5 * 60 * 1000);
      await Promise.resolve();
    });

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No assigned Pioreactors were found.")).toBeInTheDocument();
    expect(screen.queryByText(/Timed out fetching camera statuses/)).not.toBeInTheDocument();
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
                detection_status: "configured_camera_not_detected",
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

  test("shows unreachable Pioreactors without hiding reachable camera cards", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          cameras: {
            "unit-1": {
              ok: true,
              value: {
                detection_status: "detected",
                latest_still: null,
              },
            },
            "unit-2": {
              ok: false,
              error: { message: "Could not reach this Pioreactor." },
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

    expect(await screen.findByText("unit-1's Camera")).toBeInTheDocument();
    expect(screen.getByText("unit-2: Could not reach this Pioreactor.")).toBeInTheDocument();
  });

  test("keeps a Pioreactor visible when camera detection is unknown", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          cameras: {
            "unit-1": {
              ok: true,
              value: {
                detection_status: "unknown",
                latest_still: null,
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

    expect(await screen.findByText("unit-1's Camera")).toBeInTheDocument();
    expect(screen.queryByText(/No camera-capable Pioreactors/)).not.toBeInTheDocument();
  });
});
