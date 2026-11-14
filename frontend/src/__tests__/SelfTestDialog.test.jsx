import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

jest.mock("react-router", () => ({
  Link: ({ children }) => <span>{children}</span>,
}));

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({ client: null }),
}));

const SelfTestDialog = require("../components/SelfTestDialog").default;

const selfTestTests = {
  publishedSettings: {
    all_tests_passed: { value: null },
    test_pioreactor_HAT_present: { value: true },
    test_camera_capture: { value: null },
  },
};

afterEach(() => {
  jest.restoreAllMocks();
});

test.each(["detected", "configured_camera_not_detected", "unknown"])(
  "uses worker camera detection (%s) when showing self-tests",
  async (detectionStatus) => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ detection_status: detectionStatus }),
    });

    render(<SelfTestDialog unit="unit-a" experiment="$experiment" selfTestTests={selfTestTests} />);
    expect(global.fetch).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Self-test/ }));
    });

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/unit-a/camera/experiments/%24experiment/status",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
    await waitFor(() => {
      expect(Boolean(screen.queryByText("Camera captures an image"))).toBe(detectionStatus === "detected");
    });
    expect(screen.getByText("Pioreactor HAT is detected")).toBeTruthy();
    expect(screen.queryByText("Heating is responsive")).toBeNull();
  },
);

test("reports failed camera detection without blocking the other self-tests", async () => {
  global.fetch = jest.fn().mockRejectedValue(new Error("Worker unreachable"));
  render(<SelfTestDialog unit="unit-a" experiment="$experiment" selfTestTests={selfTestTests} />);
  fireEvent.click(screen.getByRole("button", { name: /Self-test/ }));

  expect(await screen.findByText(/Could not check camera availability/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Start" }).disabled).toBe(false);
  expect(screen.queryByText("Camera captures an image")).toBeNull();
});
