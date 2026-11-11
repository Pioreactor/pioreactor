import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";
import { advanceCalibrationSession } from "../utils/calibrationSessions";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;
const { MemoryRouter } = require("react-router");
const CalibrationSessionDialog = require("../components/CalibrationSessionDialog").default;
jest.mock("../utils/calibrationSessions", () => ({
  ...jest.requireActual("../utils/calibrationSessions"), advanceCalibrationSession: jest.fn(),
}));
const waitingStep = {
  step_id: "stabilize", step_type: "wait", title: "Waiting for stable temperature",
  body: "Heating and stirring are running.", poll_interval_s: 5, fields: [],
};
const probeStep = {
  step_id: "probe", step_type: "form", title: "Enter measured temperature",
  fields: [{ name: "measured_temperature", label: "Measured temperature", field_type: "float" }],
};
async function openDialog(props = {}) {
  const result = render(<MemoryRouter><CalibrationSessionDialog
    open protocol={{ title: "Trim", protocol_name: "trim", target_device: "temperature" }}
    unit="unit-1" sessionId="session-1" {...props}
  /></MemoryRouter>);
  await act(async () => {});
  return result;
}
async function tick() {
  await act(async () => { jest.advanceTimersByTime(5000); });
}
beforeEach(() => {
  jest.useFakeTimers();
  global.fetch = jest.fn(() => Promise.resolve({ ok: true, json: async () => ({
    session: { session_id: "session-1", status: "in_progress" }, step: waitingStep,
  }) }));
});
afterEach(() => { jest.useRealTimers(); jest.resetAllMocks(); });

test("resumed waiting steps poll sequentially and automatically open the probe form", async () => {
  advanceCalibrationSession.mockResolvedValueOnce({ step: waitingStep }).mockResolvedValueOnce({ step: probeStep });
  const onPause = jest.fn();
  const onClose = jest.fn();
  await openDialog({ onPause, onClose });
  expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
  expect(screen.getByRole("button", { name: "Abort" }).disabled).toBe(false);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape", code: "Escape" });
  expect(onPause).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  await tick();
  expect(advanceCalibrationSession).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("Enter measured temperature")).toBeNull();
  await tick();
  expect(screen.getByText("Enter measured temperature")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Continue" }).disabled).toBe(false);
  await tick();
  expect(advanceCalibrationSession).toHaveBeenCalledTimes(2);
});
test("abort stays available during a check and ignores its late response", async () => {
  let resolveCheck;
  advanceCalibrationSession.mockImplementation(() => new Promise((resolve) => { resolveCheck = resolve; }));
  const onClose = jest.fn();
  await openDialog({ onClose });
  await tick();
  await tick();
  expect(advanceCalibrationSession).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Abort" }));
  await act(async () => {});
  expect(onClose).toHaveBeenCalledTimes(1);
  await act(async () => { resolveCheck({ step: probeStep }); });
  expect(screen.queryByText("Enter measured temperature")).toBeNull();
});
test("a transient check failure reports the error and retries automatically", async () => {
  advanceCalibrationSession.mockRejectedValueOnce(new Error("Worker unavailable"))
    .mockResolvedValueOnce({ step: probeStep });
  await openDialog();
  await tick();
  expect(screen.getByText(/Worker unavailable.*Retrying automatically/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Abort" }).disabled).toBe(false);
  await tick();
  expect(screen.getByText("Enter measured temperature")).toBeTruthy();
});
test("unmount cancels scheduled checks", async () => {
  const view = await openDialog();
  view.unmount();
  await tick();
  expect(advanceCalibrationSession).not.toHaveBeenCalled();
});

test("failed abort cleanup remains visible and can be retried without more wait checks", async () => {
  const onClose = jest.fn();
  await openDialog({ onClose });
  global.fetch.mockResolvedValueOnce({ ok: false, status: 500,
    json: async () => ({ error: "Cleanup failed: worker unavailable" }),
  });
  fireEvent.click(screen.getByRole("button", { name: "Abort" }));
  await act(async () => {});
  expect(screen.getByText("Cleanup failed: worker unavailable")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Abort" }).disabled).toBe(false);
  await tick();
  expect(advanceCalibrationSession).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Abort" }));
  await act(async () => {});
  expect(onClose).toHaveBeenCalledTimes(1);
});
