import { advanceCalibrationSession } from "../utils/calibrationSessions";

function jsonResponse(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

describe("advanceCalibrationSession", () => {
  afterEach(() => {
    delete global.fetch;
  });

  it("polls the leader's task result after a 202", async () => {
    const step = { step_id: "next" };
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(jsonResponse(202, { task_id: "t1", status: "accepted" }))
      .mockResolvedValueOnce(jsonResponse(202, { status: "running" }))
      .mockResolvedValueOnce(jsonResponse(200, { status: "succeeded", result: { session: {}, step } }));

    const payload = await advanceCalibrationSession("pio01", "s1", { confirm: true });

    expect(payload.step).toEqual(step);
    expect(global.fetch.mock.calls[0][0]).toBe("/api/workers/pio01/calibrations/sessions/s1/inputs");
    expect(JSON.parse(global.fetch.mock.calls[0][1].body)).toEqual({ inputs: { confirm: true } });
    expect(global.fetch.mock.calls[1][0]).toBe("/api/workers/pio01/task_results/t1");
  });

  it("reports a failed step's error", async () => {
    global.fetch = jest
      .fn()
      .mockResolvedValueOnce(jsonResponse(202, { task_id: "t1" }))
      .mockResolvedValueOnce(jsonResponse(200, { status: "failed", error: "Stirring must be off before starting." }));

    await expect(advanceCalibrationSession("pio01", "s1", {})).rejects.toThrow("Stirring must be off before starting.");
  });
});
