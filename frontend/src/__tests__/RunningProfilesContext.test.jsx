import React from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { RunningProfilesProvider, useRunningProfiles } from "../providers/RunningProfilesContext";
import { runPioreactorJobViaUnitAPI } from "../utils/jobs";

jest.mock("../utils/jobs", () => ({ runPioreactorJobViaUnitAPI: jest.fn() }));

test("profile start and stop use the configured leader hostname", async () => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => [] });
  runPioreactorJobViaUnitAPI.mockResolvedValue({ ok: true });
  const wrapper = ({ children }) => (
    <RunningProfilesProvider experiment="exp-1" leaderHostname="leader-unit">
      {children}
    </RunningProfilesProvider>
  );
  const { result } = renderHook(() => useRunningProfiles(), { wrapper });
  await waitFor(() => expect(result.current.loading).toBe(false));

  jest.useFakeTimers();
  try {
    await act(async () => {
      await result.current.startProfile("profile.yaml", "exp-1", true);
      await result.current.stopProfile(42);
    });
    expect(runPioreactorJobViaUnitAPI).toHaveBeenCalledWith(
      "leader-unit", "experiment_profile", ["execute", "profile.yaml", "exp-1"], { "dry-run": null },
    );
    expect(global.fetch).toHaveBeenCalledWith("/unit_api/jobs/stop", {
      method: "POST",
      body: JSON.stringify({ job_id: 42 }),
      headers: {
        "X-Pioreactor-Target": "leader-unit",
        Accept: "application/json",
        "Content-Type": "application/json",
      },
    });
  } finally {
    jest.clearAllTimers();
    jest.useRealTimers();
  }
});
