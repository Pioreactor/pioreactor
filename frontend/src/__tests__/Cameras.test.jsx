import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: {},
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
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

  test("coalesces camera notifications while a refresh is in progress", async () => {
    let finishRefresh;
    const emptyCameraResponse = {
      ok: true,
      json: () => Promise.resolve({ cameras: {} }),
    };
    global.fetch = jest.fn()
      .mockResolvedValueOnce(emptyCameraResponse)
      .mockImplementationOnce(() => new Promise((resolve) => {
        finishRefresh = () => resolve(emptyCameraResponse);
      }))
      .mockResolvedValue(emptyCameraResponse);

    render(
      <MemoryRouter>
        <Cameras title="Cameras" />
      </MemoryRouter>,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
    const onCameraStillChanged = mockSubscribeToTopic.mock.calls[0][1];

    act(() => {
      for (let index = 0; index < 12; index += 1) {
        onCameraStillChanged(
          `pioreactor/unit-${index}/experiment-a/camera/latest_still`,
          Buffer.from("{}"),
          { retain: false },
        );
      }
    });

    expect(global.fetch).toHaveBeenCalledTimes(2);

    finishRefresh();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(3));
  });

  test("coalesces retained camera notifications received during the initial load", async () => {
    let finishInitialLoad;
    const emptyCameraResponse = {
      ok: true,
      json: () => Promise.resolve({ cameras: {} }),
    };
    global.fetch = jest.fn()
      .mockImplementationOnce(() => new Promise((resolve) => {
        finishInitialLoad = () => resolve(emptyCameraResponse);
      }))
      .mockResolvedValue(emptyCameraResponse);

    render(
      <MemoryRouter>
        <Cameras title="Cameras" />
      </MemoryRouter>,
    );

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
    const onCameraStillChanged = mockSubscribeToTopic.mock.calls[0][1];

    act(() => {
      for (let index = 0; index < 12; index += 1) {
        onCameraStillChanged(
          `pioreactor/unit-${index}/experiment-a/camera/latest_still`,
          Buffer.from("{}"),
          { retain: true },
        );
      }
    });

    expect(global.fetch).toHaveBeenCalledTimes(1);

    finishInitialLoad();
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
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
