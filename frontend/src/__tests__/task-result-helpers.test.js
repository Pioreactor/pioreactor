import { assertUnitTaskResultSucceeded } from "../utils/tasks";

describe("assertUnitTaskResultSucceeded", () => {
  test("accepts a successful result for the requested unit", () => {
    expect(() =>
      assertUnitTaskResultSucceeded(
        { result: { "unit-1": { status: "success" } } },
        "unit-1",
        "Fallback failure.",
      ),
    ).not.toThrow();
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
        { result: { "unit-1": { error: "Worker rejected this request." } } },
        "unit-1",
        "Fallback failure.",
      ),
    ).toThrow("Worker rejected this request.");
  });
});
