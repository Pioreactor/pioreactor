import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockFetchTaskResult = jest.fn();

jest.mock("../utils/tasks", () => {
  const actual = jest.requireActual("../utils/tasks");
  return {
    ...actual,
    fetchTaskResult: (...args) => mockFetchTaskResult(...args),
  };
});

const { MemoryRouter } = require("react-router");
const CameraPanel = require("../components/CameraPanel").default;

describe("CameraPanel", () => {
  afterEach(() => {
    jest.useRealTimers();
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

  test("loads status and the latest snapshot from the selected experiment", async () => {
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
    expect(await screen.findByAltText("Latest camera snapshot for unit-1")).toHaveAttribute(
      "src",
      "/api/workers/unit-1/camera/experiments/experiment-a/stills/image-1.jpg",
    );
  });

  test("polls status at the snapshot interval when it owns the request", async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          available: true,
          latest_still: null,
          snapshot_interval_minutes: 1,
        }),
      }),
    );

    render(
      <MemoryRouter>
        <CameraPanel unit="unit-1" experiment="experiment-a" />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByText("No camera snapshot")).toBeInTheDocument();

    await act(async () => {
      jest.advanceTimersByTime(60 * 1000);
      await Promise.resolve();
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledTimes(2);
    });
  });

  test("updates automatic snapshots through the worker settings route", async () => {
    mockFetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": { ok: true, value: { auto_capture_enabled: false } },
      },
    });

    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          initialStatus={{ available: true, auto_capture_enabled: true }}
        />
      </MemoryRouter>,
    );

    const automaticStillsSwitch = screen.getByRole("switch", { name: "Capture snapshots automatically" });
    expect(automaticStillsSwitch).toBeChecked();

    fireEvent.click(automaticStillsSwitch);

    expect(mockFetchTaskResult).toHaveBeenCalledWith(
      "/api/workers/unit-1/camera/settings",
      {
        fetchOptions: {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_capture_enabled: false }),
        },
      },
    );
    await waitFor(() => expect(automaticStillsSwitch).not.toBeChecked());
  });

  test("restores automatic snapshots and explains a failed update", async () => {
    let rejectUpdate;
    mockFetchTaskResult.mockImplementation(
      () => new Promise((_resolve, reject) => {
        rejectUpdate = reject;
      }),
    );

    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          initialStatus={{ available: true, auto_capture_enabled: true }}
        />
      </MemoryRouter>,
    );

    const automaticStillsSwitch = screen.getByRole("switch", { name: "Capture snapshots automatically" });
    fireEvent.click(automaticStillsSwitch);

    expect(automaticStillsSwitch).not.toBeChecked();
    expect(automaticStillsSwitch).toBeDisabled();

    rejectUpdate(new Error("Worker could not save the setting."));

    expect(await screen.findByText(/Could not update automatic snapshots/)).toHaveTextContent(
      "Could not update automatic snapshots. Worker could not save the setting.",
    );
    expect(automaticStillsSwitch).toBeChecked();
    expect(automaticStillsSwitch).not.toBeDisabled();
  });
});
