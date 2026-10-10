import { jobEnv } from "../kiosk/context";
import { applyKey, validateNumber } from "../kiosk/Keyboard";
import { topicMatches } from "../kiosk/mqtt";

jest.mock("mqtt", () => ({ connect: jest.fn() }));

describe("kiosk topicMatches", () => {
  it("matches single-level and multi-level wildcards", () => {
    expect(topicMatches("pioreactor/u1/exp/+/+", "pioreactor/u1/exp/stirring/$state")).toBe(true);
    expect(topicMatches("pioreactor/u1/exp/+/+", "pioreactor/u1/exp/stirring/target_rpm/set")).toBe(false);
    expect(topicMatches("pioreactor/u1/exp/+/+", "pioreactor/u2/exp/stirring/$state")).toBe(false);
    expect(topicMatches("pioreactor/u1/#", "pioreactor/u1/exp/logs/app/info")).toBe(true);
    expect(topicMatches("pioreactor/u1/$experiment/assignment", "pioreactor/u1/$experiment/assignment")).toBe(true);
  });
});

describe("kiosk jobEnv", () => {
  it("adds the values the leader would add when it knows the worker", () => {
    expect(jobEnv({ experiment: "exp", worker: { is_active: 1, model_name: "pioreactor_40ml", model_version: "1.5" } })).toEqual({
      EXPERIMENT: "exp",
      JOB_SOURCE: "user",
      ACTIVE: "1",
      MODEL_NAME: "pioreactor_40ml",
      MODEL_VERSION: "1.5",
    });
    expect(jobEnv({ experiment: "exp", worker: undefined })).toEqual({ EXPERIMENT: "exp", JOB_SOURCE: "user" });
  });
});

describe("kiosk keyboard editing", () => {
  it("replaces a pre-filled value on the first keystroke", () => {
    const state = applyKey({ text: "500", caret: 3, fresh: true }, "6");
    expect(state).toEqual({ text: "6", caret: 1, fresh: false });
  });

  it("validates number limits", () => {
    expect(validateNumber("5", { min: 10 })).toBe("Must be at least 10.");
    expect(validateNumber("-1", { allowNegative: false })).toBe("Must not be negative.");
    expect(validateNumber("2.5", { integer: true })).toBe("Must be a whole number.");
    expect(validateNumber("12", { min: 10, max: 20 })).toBeNull();
  });
});
