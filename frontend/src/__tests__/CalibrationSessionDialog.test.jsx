import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const CalibrationSessionDialog = require("../components/CalibrationSessionDialog").default;

describe("CalibrationSessionDialog", () => {
  beforeEach(() => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions") {
        throw new Error("Dialog should not start a new session when a sessionId prop is present.");
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              session: {
                session_id: "session-1",
                status: "in_progress",
              },
              step: {
                step_id: "run_calibration",
                step_type: "action",
                title: "Record calibration",
                body: "Run the hardware action.",
                fields: [],
                metadata: { primary_action_label: "Take snapshot" },
              },
            }),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/abort") {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ error: "Cleanup failed: stirring is still running." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("keeps the dialog open and surfaces server abort errors", async () => {
    const onAbortSuccess = jest.fn();
    const onAbortFailure = jest.fn();
    const onClose = jest.fn();

    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Test protocol", protocol_name: "dummy", target_device: "device" }}
          unit="unit-1"
          sessionId="session-1"
          onAbortSuccess={onAbortSuccess}
          onAbortFailure={onAbortFailure}
          onClose={onClose}
        />
      </MemoryRouter>,
    );

    await screen.findByText("Record calibration");

    fireEvent.click(screen.getByText("Abort"));

    await screen.findByText("Cleanup failed: stirring is still running.");

    expect(onAbortSuccess).not.toHaveBeenCalled();
    expect(onAbortFailure).toHaveBeenCalledWith("Cleanup failed: stirring is still running.");
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByText("Record calibration")).toBeTruthy();

    expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions/session-1/abort",
      expect.objectContaining({ method: "POST" }),
    );
  });

  test("loads the existing session step instead of starting over when resumed", async () => {
    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Test protocol", protocol_name: "dummy", target_device: "device" }}
          unit="unit-1"
          sessionId="session-1"
        />
      </MemoryRouter>,
    );

    await screen.findByText("Record calibration");
    expect(screen.getByRole("button", { name: "Take snapshot" })).toBeTruthy();

    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit-1/calibrations/sessions/session-1");
    expect(global.fetch).not.toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions",
      expect.anything(),
    );
  });

  test("uses the protocol target_device when the completion result omits the calibration device", async () => {
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions/session-1") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              session: {
                session_id: "session-1",
                status: "complete",
              },
              step: {
                step_id: "complete",
                step_type: "complete",
                title: "Calibration complete",
                body: "Saved calibration.",
                result: {
                  calibration: {
                    calibration_name: "alt_media_pump-2026-04-13",
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
        <CalibrationSessionDialog
          open
          protocol={{
            title: "Alt-media pump calibration",
            protocol_name: "dummy",
            target_device: "alt_media_pump",
          }}
          unit="unit-1"
          sessionId="session-1"
        />
      </MemoryRouter>,
    );

    const calibrationLink = await screen.findByRole("link", {
      name: "alt_media_pump-2026-04-13",
    });

    expect(calibrationLink).toHaveAttribute(
      "href",
      "/calibrations/unit-1/alt_media_pump/alt_media_pump-2026-04-13",
    );
  });

  test("shows score-free focus guidance and updates it after another snapshot", async () => {
    const focusStep = (status, message, snapshotCount, guidanceImage) => ({
      step_id: "focus_camera",
      step_type: "info",
      title: "Adjust the camera focus",
      body: "Turn the camera's focus control until fine details look sharp.",
      fields: [],
      metadata: {
        image: {
          src: `/api/workers/unit-1/camera/focus_sessions/session-1/preview.jpg?v=${snapshotCount}`,
          alt: "Camera focus snapshot from unit-1.",
          caption: `Focus snapshot ${snapshotCount}`,
          max_height: 520,
          aspect_ratio: "4 / 3",
          enlargeable: true,
        },
        actions: [
          {
            label: "Take another snapshot",
            inputs: { action: "retake" },
            updates_image: true,
          },
        ],
        dialog: { max_width: "md", height: "min(90vh, 860px)" },
        guidance: {
          title: "Focus guidance",
          status,
          message,
          ...(guidanceImage ? { image: guidanceImage } : {}),
        },
        primary_action_label: "Focus is complete",
      },
    });

    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions/session-1") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              step: focusStep(
                "initial",
                "Adjust the focus slightly, then take another snapshot.",
                1,
                {
                  src: "/static/svgs/camera-focus-tool-concept-02-sequence.svg",
                  alt: "Fit the focusing tool over the camera lens, then rotate the handle in either direction.",
                },
              ),
            }),
        });
      }

      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/inputs") {
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
              result: { step: focusStep("blurrier", "Blurrier — turn back slightly.", 2) },
            }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Manual camera focus", protocol_name: "manual_focus", target_device: "camera" }}
          unit="unit-1"
          sessionId="session-1"
        />
      </MemoryRouter>,
    );

    await screen.findByText("Adjust the focus slightly, then take another snapshot.");
    const firstImage = screen.getByRole("img", { name: "Camera focus snapshot from unit-1." });
    expect(screen.getByText("Focus guidance").closest("[aria-live='polite']")).toBeTruthy();
    expect(screen.queryByText(/FocusFoM/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/best this session/i)).not.toBeInTheDocument();
    expect(screen.getByText("Loading image...")).toBeInTheDocument();

    fireEvent.load(firstImage);

    expect(screen.queryByText("Loading image...")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Enlarge image: Focus snapshot 1" }));

    const enlargedImageDialog = screen.getByRole("dialog", { name: "Focus snapshot 1" });
    expect(
      within(enlargedImageDialog).getByRole("img", {
        name: "Camera focus snapshot from unit-1.",
      }),
    ).toHaveAttribute(
      "src",
      "/api/workers/unit-1/camera/focus_sessions/session-1/preview.jpg?v=1",
    );

    fireEvent.click(within(enlargedImageDialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog", { name: "Focus snapshot 1" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Take another snapshot" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Take another snapshot" }));

    expect(screen.getByText("Loading image...")).toBeInTheDocument();

    await screen.findByText("Blurrier — turn back slightly.");
    const secondImage = screen.getByRole("img", { name: "Camera focus snapshot from unit-1." });
    expect(secondImage).toHaveAttribute(
      "src",
      "/api/workers/unit-1/camera/focus_sessions/session-1/preview.jpg?v=2",
    );
    expect(screen.getByText("Loading image...")).toBeInTheDocument();

    fireEvent.load(secondImage);

    expect(screen.queryByText("Loading image...")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Adjust the focus slightly, then take another snapshot."),
    ).not.toBeInTheDocument();
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/unit-1/calibrations/sessions/session-1/inputs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ inputs: { action: "retake" } }),
      }),
    );
  });

  test("lets the user correct and exclude recorded rows before saving", async () => {
    const reviewStep = {
      step_id: "review_data",
      step_type: "form",
      title: "Review data",
      body: "Check the recorded data before saving.",
      fields: [
        {
          name: "recorded_data",
          label: "Recorded data",
          field_type: "data_table",
          columns: [
            { key: "run", label: "Run", editable: false, minimum: null },
            { key: "duration", label: "Duration (s)", editable: false, minimum: null },
            { key: "volume", label: "Volume (mL)", editable: true, minimum: 0.0001 },
          ],
          default: [
            { run: 1, duration: 1.0, volume: 0.5, include: true },
            { run: 2, duration: 2.0, volume: 10.0, include: true },
            { run: 3, duration: 3.0, volume: 1.5, include: true },
          ],
        },
      ],
      metadata: {
        primary_action_label: "Save calibration",
        actions: [{ label: "Update chart", inputs: { action: "preview" }, include_values: true }],
      },
    };

    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/calibrations/sessions/session-1") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ step: reviewStep }) });
      }
      if (url === "/api/workers/unit-1/calibrations/sessions/session-1/inputs") {
        return Promise.resolve({ ok: true, status: 202, json: () => Promise.resolve({ task_id: "task-1" }) });
      }
      if (url === "/api/workers/unit-1/task_results/task-1") {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ status: "succeeded", result: { step: reviewStep } }),
        });
      }
      throw new Error(`Unexpected fetch call: ${url}`);
    });

    render(
      <MemoryRouter>
        <CalibrationSessionDialog
          open
          protocol={{ title: "Pump calibration", protocol_name: "duration_based", target_device: "media_pump" }}
          unit="unit-1"
          sessionId="session-1"
        />
      </MemoryRouter>,
    );

    const volumeInput = await screen.findByRole("textbox", { name: "Volume (mL) for Run 2" });
    const saveButton = screen.getByRole("button", { name: "Save calibration" });

    fireEvent.change(volumeInput, { target: { value: "" } });
    expect(screen.getByText("Required")).toBeInTheDocument();
    expect(saveButton).toBeDisabled();
    expect(screen.getByRole("button", { name: "Update chart" })).toBeDisabled();

    fireEvent.change(volumeInput, { target: { value: "1.0" } });
    expect(saveButton).toBeEnabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use Run 3 in fit" }));
    fireEvent.click(screen.getByRole("button", { name: "Update chart" }));

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workers/unit-1/calibrations/sessions/session-1/inputs",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            inputs: {
              recorded_data: [
                { run: 1, duration: 1.0, volume: 0.5, include: true },
                { run: 2, duration: 2.0, volume: 1.0, include: true },
                { run: 3, duration: 3.0, volume: 1.5, include: false },
              ],
              action: "preview",
            },
          }),
        }),
      );
    });
  });
});
