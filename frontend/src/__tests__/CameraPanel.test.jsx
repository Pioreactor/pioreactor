import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockFetchTaskResult = jest.fn();

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: null,
    subscribeToTopic: jest.fn(),
    unsubscribeFromTopic: jest.fn(),
  }),
}));

jest.mock("../utils/tasks", () => {
  const actual = jest.requireActual("../utils/tasks");
  return {
    ...actual,
    fetchTaskResult: (...args) => mockFetchTaskResult(...args),
  };
});

const { MemoryRouter } = require("react-router");
const CameraPanel = require("../components/CameraPanel").default;


function ControlledCameraPanel({ initialStatus, ...props }) {
  const [status, setStatus] = React.useState(initialStatus);
  return <CameraPanel {...props} status={status} onStatusChange={setStatus} />;
}

describe("CameraPanel", () => {
  afterEach(() => {
    jest.useRealTimers();
    jest.resetAllMocks();
  });

  test("shows the latest photo metadata in the enlarged viewer", async () => {
    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          experimentStartTime="2026-06-11T10:30:00Z"
          status={{
            detection_status: "detected",
            latest_still: {
              image_id: "image-1",
              captured_at: "2026-06-11T12:00:00Z",
              capture_reason: "manual",
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

    fireEvent.click(screen.getByRole("button", { name: "Latest camera snapshot for unit-1" }));

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("unit-1")).toBeInTheDocument();
    expect(within(dialog).getByText("image-1")).toBeInTheDocument();
    expect(within(dialog).getByText(
      dayjs("2026-06-11T12:00:00Z").format("YYYY-MM-DD HH:mm:ss"),
    )).toBeInTheDocument();
    const captureReasonIcon = within(dialog).getByRole("img", { name: "Manual snapshot" });
    expect(captureReasonIcon).toHaveAttribute("data-testid", "LocalSeeIcon");
    fireEvent.mouseOver(captureReasonIcon);
    expect(await screen.findByRole("tooltip", { name: "Manual snapshot" })).toBeInTheDocument();
  });

  test("loads status and the latest snapshot from the selected experiment", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          detection_status: "detected",
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

  test("uses a low-frequency recovery refresh when it owns the request", async () => {
    jest.useFakeTimers();
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          detection_status: "detected",
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
      jest.advanceTimersByTime(5 * 60 * 1000);
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
        <ControlledCameraPanel
          unit="unit-1"
          experiment="experiment-a"
          initialStatus={{ detection_status: "detected", auto_capture_enabled: true }}
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
        <ControlledCameraPanel
          unit="unit-1"
          experiment="experiment-a"
          initialStatus={{ detection_status: "detected", auto_capture_enabled: true }}
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

  test("distinguishes an unknown detection result from a missing camera", () => {
    render(
      <MemoryRouter>
        <CameraPanel
          unit="unit-1"
          experiment="experiment-a"
          status={{ detection_status: "unknown", latest_still: null }}
        />
      </MemoryRouter>,
    );

  });
});
