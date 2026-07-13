import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";
import dayjs from "dayjs";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockConfirm = jest.fn();
const mockAssertUnitTaskResultSucceeded = jest.fn();
const mockFetchTaskResult = jest.fn();

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
          element={<CameraStills title="Camera stills" />}
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

  test("confirms and removes a deleted still from the timeline", async () => {
    const user = userEvent.setup();
    renderCameraStills();

    const deleteButton = await screen.findByRole("button", {
      name: /Delete camera still captured at/,
    });
    await user.click(deleteButton);

    expect(mockConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Delete this camera still?",
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
        name: /Delete camera still captured at/,
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

  test("initially mounts only the newest 24 stills", async () => {
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));

    renderCameraStills();

    const images = await screen.findAllByRole("img");
    expect(images).toHaveLength(24);
    expect(images[0]).toHaveAttribute("src", expect.stringContaining("image-30.jpg"));
    expect(images[23]).toHaveAttribute("src", expect.stringContaining("image-7.jpg"));
    expect(screen.getByRole("button", { name: "Load earlier" })).toBeInTheDocument();
  });

  test("loads the next batch of earlier stills", async () => {
    const user = userEvent.setup();
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));
    renderCameraStills();

    await user.click(await screen.findByRole("button", { name: "Load earlier" }));

    expect(screen.getAllByRole("img")).toHaveLength(30);
    expect(screen.getAllByRole("img")[29]).toHaveAttribute(
      "src",
      expect.stringContaining("image-1.jpg"),
    );
    expect(screen.queryByRole("button", { name: "Load earlier" })).not.toBeInTheDocument();
  });

  test("preserves the visible window when refreshed with a new still", async () => {
    const user = userEvent.setup();
    cameraStills = Array.from({ length: 30 }, (_, index) => ({
      image_id: `image-${index + 1}`,
      captured_at: dayjs("2026-06-10T00:00:00Z").add(index, "hour").toISOString(),
      experiment: "experiment a",
    }));
    renderCameraStills();

    await user.click(await screen.findByRole("button", { name: "Load earlier" }));
    expect(screen.getAllByRole("img")).toHaveLength(30);

    cameraStills = [
      ...cameraStills,
      {
        image_id: "image-31",
        captured_at: dayjs("2026-06-10T00:00:00Z").add(30, "hour").toISOString(),
        experiment: "experiment a",
      },
    ];
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(31));
    expect(screen.getAllByRole("img")[0]).toHaveAttribute(
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

    await screen.findByRole("img");
    await user.click(screen.getByRole("button", { name: "Refresh" }));

    expect(mockFetchTaskResult).toHaveBeenCalledWith(
      "/api/workers/unit-1/camera/experiments/experiment%20a/stills",
      { fetchOptions: { method: "POST" }, maxRetries: 300, delayMs: 100 },
    );
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
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

  test("uses a native attachment link for downloading all stills", async () => {
    renderCameraStills();

    const downloadAll = await screen.findByRole("link", { name: "Download All" });

    expect(downloadAll).toHaveAttribute(
      "href",
      "/api/workers/unit-1/camera/experiments/experiment%20a/stills.zip",
    );
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
