import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockConfirm = jest.fn();
const mockAssertUnitTaskResultSucceeded = jest.fn();
const mockFetchTaskResult = jest.fn();
const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
const mockMqttClient = {};

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: mockMqttClient,
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => mockConfirm,
}));

jest.mock("../utils/tasks", () => ({
  assertUnitTaskResultSucceeded: (...args) => mockAssertUnitTaskResultSucceeded(...args),
  fetchTaskResult: (...args) => mockFetchTaskResult(...args),
}));

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: {
      experiment: "experiment a",
      created_at: "2026-06-11T10:30:00Z",
    },
  }),
}));

const CameraStills = require("../CameraStills").default;
const { MemoryRouter, Route, Routes } = require("react-router");

let cameraStills;

function renderCameraStills() {
  return render(
    <MemoryRouter initialEntries={["/cameras/unit-1"]}>
      <Routes>
        <Route
          path="/cameras/:pioreactorUnit"
          element={<CameraStills title="Camera snapshots" />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CameraStills", () => {
  beforeEach(() => {
    mockConfirm.mockResolvedValue();
    mockFetchTaskResult.mockResolvedValue({
      result: {
        "unit-1": { ok: true, value: { image_id: "image-2" } },
      },
    });
    cameraStills = [
      {
        image_id: "image-1",
        captured_at: "2026-06-11T12:00:00Z",
        experiment: "experiment a",
        capture_reason: "scheduled",
      },
    ];
    global.fetch = jest.fn((url, options = {}) => {
      if (options.method === "DELETE") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ image_id: "image-1" }),
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          snapshot_interval_minutes: 0,
          stills: cameraStills,
        }),
      });
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("identifies the camera unit below the page toolbar", async () => {
    renderCameraStills();

    expect(await screen.findByRole("heading", { level: 1, name: "Camera snapshots on unit-1" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to cameras" })).toHaveAttribute("href", "/cameras");
    expect(screen.getByRole("separator")).toBeInTheDocument();
  });

  test("shows progress while downloading all snapshots", async () => {
    const user = userEvent.setup();
    const archive = new Blob(["camera archive"], { type: "application/zip" });
    let finishDownload;
    const createObjectURL = jest.fn(() => "blob:camera-snapshots");
    const revokeObjectURL = jest.fn();
    const clickDownloadLink = jest.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    Object.defineProperty(window.URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(window.URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });
    global.fetch = jest.fn((url) => {
      if (url.endsWith("stills.zip")) {
        return new Promise((resolve) => {
          finishDownload = () => resolve({
            ok: true,
            blob: () => Promise.resolve(archive),
          });
        });
      }

      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          snapshot_interval_minutes: 0,
          stills: cameraStills,
        }),
      });
    });
    renderCameraStills();

    const downloadButton = await screen.findByRole("button", { name: "Download all snapshots" });
    await user.click(downloadButton);

    expect(global.fetch).toHaveBeenLastCalledWith(
      "/api/workers/unit-1/camera/experiments/experiment%20a/stills.zip",
    );
    expect(downloadButton).toBeDisabled();
    expect(within(downloadButton).getByRole("progressbar")).toBeInTheDocument();

    finishDownload();

    await waitFor(() => expect(downloadButton).not.toBeDisabled());
    expect(createObjectURL).toHaveBeenCalledWith(archive);
    expect(clickDownloadLink).toHaveBeenCalledTimes(1);
    expect(clickDownloadLink.mock.instances[0]).toHaveAttribute(
      "download",
      "unit-1_experiment a_camera_snapshots.zip",
    );
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:camera-snapshots");
  });

  test("confirms and removes a deleted snapshot from the timeline", async () => {
    const user = userEvent.setup();
    renderCameraStills();

    const deleteButton = await screen.findByRole("button", {
      name: /Delete camera snapshot captured at/,
    });
    await user.click(deleteButton);

    expect(mockConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Delete this camera snapshot?",
        confirmationText: "Delete",
      }),
    );
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workers/unit-1/camera/experiments/experiment%20a/stills/image-1.jpg",
        { method: "DELETE" },
      ),
    );
    expect(
      screen.queryByRole("button", {
        name: /Delete camera snapshot captured at/,
      }),
    ).not.toBeInTheDocument();
  });

  test("shows capture time since the experiment began with the timestamp in a tooltip", async () => {
    renderCameraStills();

    const captureTime = await screen.findByText("1.5 h");

    expect(captureTime).toHaveAttribute(
      "aria-label",
      dayjs("2026-06-11T12:00:00Z").format("YYYY-MM-DD HH:mm:ss"),
    );
  });

  test("shows informational icons for scheduled and manual snapshots", async () => {
    const user = userEvent.setup();
    cameraStills = [
      cameraStills[0],
      {
        image_id: "image-2",
        captured_at: "2026-06-11T12:05:00Z",
        experiment: "experiment a",
        capture_reason: "manual",
      },
    ];

    renderCameraStills();

    const scheduledIcon = await screen.findByRole("img", { name: "Scheduled snapshot" });
    const manualIcon = screen.getByRole("img", { name: "Manual snapshot" });
    expect(scheduledIcon).toHaveAttribute("data-testid", "ScheduleIcon");
    expect(manualIcon).toHaveAttribute("data-testid", "LocalSeeIcon");
    expect(within(screen.getByRole("button", { name: "Capture snapshot" })).getByTestId("LocalSeeIcon")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Scheduled snapshot" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Manual snapshot" })).not.toBeInTheDocument();

    await user.hover(scheduledIcon);
    expect(await screen.findByRole("tooltip", { name: "Scheduled snapshot" })).toBeInTheDocument();
    await user.unhover(scheduledIcon);
    await user.hover(manualIcon);
    expect(await screen.findByRole("tooltip", { name: "Manual snapshot" })).toBeInTheDocument();
  });

  test("uses labeled icon buttons for snapshot actions", async () => {
    const user = userEvent.setup();
    renderCameraStills();

    const deleteButton = await screen.findByRole("button", {
      name: /Delete camera snapshot captured at/,
    });
    const openImageLink = screen.getByRole("link", { name: "Open image" });
    expect(within(deleteButton).getByTestId("DeleteOutlinedIcon")).toBeInTheDocument();
    expect(within(openImageLink).getByTestId("FullscreenIcon")).toBeInTheDocument();
    expect(deleteButton).not.toHaveTextContent("Delete");
    expect(openImageLink).not.toHaveTextContent("Open image");

    await user.hover(deleteButton);
    expect(await screen.findByRole("tooltip", { name: "Delete snapshot" })).toBeInTheDocument();
    await user.unhover(deleteButton);
    await user.hover(openImageLink);
    expect(await screen.findByRole("tooltip", { name: "Open image" })).toBeInTheDocument();
  });

  test("enlarges snapshots and navigates through them with the arrow keys", async () => {
    const user = userEvent.setup();
    cameraStills = [
      cameraStills[0],
      {
        image_id: "image-2",
        captured_at: "2026-06-11T12:05:00Z",
        experiment: "experiment a",
        capture_reason: "manual",
      },
    ];
    renderCameraStills();

    const enlargeButtons = await screen.findAllByRole("button", {
      name: /Enlarge camera snapshot captured at/,
    });
    await user.click(enlargeButtons[0]);

    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("img", { name: /Enlarged camera snapshot/ })).toHaveAttribute(
      "src",
      expect.stringContaining("image-2.jpg"),
    );
    expect(within(dialog).queryByRole("button", { name: "Previous snapshot" })).not.toBeInTheDocument();
    expect(within(dialog).queryByRole("button", { name: "Next snapshot" })).not.toBeInTheDocument();

    await user.keyboard("{ArrowRight}");

    expect(within(dialog).getByRole("img", { name: /Enlarged camera snapshot/ })).toHaveAttribute(
      "src",
      expect.stringContaining("image-1.jpg"),
    );

    await user.keyboard("{ArrowLeft}");

    expect(within(dialog).getByRole("img", { name: /Enlarged camera snapshot/ })).toHaveAttribute(
      "src",
      expect.stringContaining("image-2.jpg"),
    );
  });

  test("initially mounts only the newest 24 snapshots", async () => {
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));

    renderCameraStills();

    const images = await screen.findAllByRole("img", { name: /Camera snapshot from unit-1/ });
    expect(images).toHaveLength(24);
    expect(images[0]).toHaveAttribute("src", expect.stringContaining("image-30.jpg"));
    expect(images[23]).toHaveAttribute("src", expect.stringContaining("image-7.jpg"));
    expect(screen.getByRole("button", { name: "Load earlier" })).toBeInTheDocument();
  });

  test("loads the next batch of earlier snapshots", async () => {
    const user = userEvent.setup();
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));
    renderCameraStills();

    await user.click(await screen.findByRole("button", { name: "Load earlier" }));

    expect(screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ })).toHaveLength(30);
    expect(screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ })[29]).toHaveAttribute(
      "src",
      expect.stringContaining("image-1.jpg"),
    );
    expect(screen.queryByRole("button", { name: "Load earlier" })).not.toBeInTheDocument();
  });

  test("preserves the visible window when refreshed with a new snapshot", async () => {
    const user = userEvent.setup();
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));
    renderCameraStills();

    await user.click(await screen.findByRole("button", { name: "Load earlier" }));
    expect(screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ })).toHaveLength(30);

    cameraStills = [
      ...cameraStills,
      {
        image_id: "image-31",
        captured_at: dayjs("2026-06-10T00:00:00Z").add(30, "hour").toISOString(),
        experiment: "experiment a",
      },
    ];
    await user.click(screen.getByRole("button", { name: "Capture snapshot" }));

    await waitFor(() => expect(
      screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ }),
    ).toHaveLength(31));
    expect(screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ })[0]).toHaveAttribute(
      "src",
      expect.stringContaining("image-31.jpg"),
    );
  });

  test("takes a camera snapshot before refreshing the timeline", async () => {
    const user = userEvent.setup();
    let finishSnapshot;
    mockFetchTaskResult.mockReturnValue(new Promise((resolve) => {
      finishSnapshot = resolve;
    }));
    renderCameraStills();

    await screen.findByRole("img", { name: /Camera snapshot from unit-1/ });
    await user.click(screen.getByRole("button", { name: "Capture snapshot" }));

    expect(mockFetchTaskResult).toHaveBeenCalledWith(
      "/api/workers/unit-1/camera/experiments/experiment%20a/stills",
      { fetchOptions: { method: "POST" }, maxRetries: 300, delayMs: 100 },
    );
    expect(screen.getByRole("button", { name: "Capture snapshot" })).toBeDisabled();
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const taskResult = {
      result: {
        "unit-1": { ok: true, value: { image_id: "image-2" } },
      },
    };
    finishSnapshot(taskResult);

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    expect(mockAssertUnitTaskResultSucceeded).toHaveBeenCalledWith(
      taskResult,
      "unit-1",
      "Could not take a camera snapshot on unit-1.",
    );
    expect(global.fetch).toHaveBeenLastCalledWith(
      "/api/workers/unit-1/camera/experiments/experiment%20a/stills",
      { signal: undefined },
    );
  });

  test("keeps existing snapshots visible when a background refresh fails", async () => {
    const user = userEvent.setup();
    let requestCount = 0;
    global.fetch = jest.fn(() => {
      requestCount += 1;
      if (requestCount === 1) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ stills: cameraStills }),
        });
      }

      return Promise.resolve({
        ok: false,
        json: () => Promise.resolve({ error: "Could not refresh camera snapshots." }),
      });
    });
    renderCameraStills();

    const existingSnapshot = await screen.findByRole("img", { name: /Camera snapshot from unit-1/ });
    await user.click(screen.getByRole("button", { name: "Capture snapshot" }));

    expect(await screen.findByText(/Could not refresh camera snapshots/)).toBeInTheDocument();
    expect(existingSnapshot).toBeInTheDocument();
  });

  test("refreshes the timeline when the worker publishes a new still", async () => {
    renderCameraStills();
    await screen.findByRole("img", { name: /Camera snapshot from unit-1/ });
    cameraStills = [
      ...cameraStills,
      {
        image_id: "image-2",
        captured_at: "2026-06-11T12:05:00Z",
        experiment: "experiment a",
        capture_reason: "scheduled",
      },
    ];

    const subscribedTopic = `pioreactor/unit-1/experiment a/camera/latest_still`;
    const subscription = mockSubscribeToTopic.mock.calls.find(([topic]) => topic === subscribedTopic);
    expect(subscription).toBeDefined();
    subscription[1](subscribedTopic, Buffer.from("{}"));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(
      screen.getAllByRole("img", { name: /Camera snapshot from unit-1/ })
        .some((image) => image.getAttribute("src").includes("image-2.jpg")),
    ).toBe(true));
  });
});
