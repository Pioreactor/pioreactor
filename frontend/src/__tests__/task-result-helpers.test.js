import {
  assertUnitTaskResultSucceeded,
  getSuccessfulUnitTaskResults,
  getUnitTaskResult,
} from "../utils/tasks";

describe("assertUnitTaskResultSucceeded", () => {
  test("accepts a successful result for the requested unit", () => {
    const payload = { result: { "unit-1": { ok: true, unit: "unit-1", value: { rpm: 500 } } } };

    expect(getUnitTaskResult(payload, "unit-1", "Fallback failure.")).toEqual({ rpm: 500 });
    expect(() => assertUnitTaskResultSucceeded(payload, "unit-1", "Fallback failure.")).not.toThrow();
  });

  test("rejects a null result for the requested unit", () => {
    expect(() =>
      assertUnitTaskResultSucceeded(
        { result: { "unit-1": null } },
        "unit-1",
        "Fallback failure.",
      ),
    ).toThrow("Fallback failure.");
  });

  test("uses unit error text when present", () => {
    expect(() =>
      assertUnitTaskResultSucceeded(
        {
          result: {
            "unit-1": {
              ok: false,
              unit: "unit-1",
              error: { kind: "http_error", message: "Worker rejected this request." },
              status_code: 400,
              retryable: false,
            },
          },
        },
        "unit-1",
        "Fallback failure.",
      ),
    ).toThrow("Worker rejected this request.");
  });

  test("rejects legacy unit payloads without ok", () => {
    expect(() =>
      getUnitTaskResult(
        { result: { "unit-1": { status: "success" } } },
        "unit-1",
        "Fallback failure.",
      ),
    ).toThrow("Fallback failure.");
  });

  test("returns only successful fanout values", () => {
    expect(
      getSuccessfulUnitTaskResults({
        result: {
          "unit-1": { ok: true, unit: "unit-1", value: { rpm: 500 } },
          "unit-2": {
            ok: false,
            unit: "unit-2",
            error: { kind: "connection_error", message: "Could not reach unit-2." },
            status_code: null,
            retryable: true,
          },
        },
      }),
    ).toEqual({ "unit-1": { rpm: 500 } });
  });
});
