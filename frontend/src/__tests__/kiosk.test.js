import { validateExperimentName, validateUnitName } from "../kiosk/cluster";
import { jobEnv, parseAssignment, roleOf } from "../kiosk/context";
import { applyKey, validateNumber } from "../kiosk/Keyboard";
import { topicMatches } from "../kiosk/mqtt";
import {
  connectWifi,
  finishOnboarding,
  getOnboarding,
  listModels,
  MOCK_MODELS,
  resetOnboarding,
} from "../kiosk/onboardingApi";

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
  it("passes the experiment and active flag the leader would pass, not the model", () => {
    expect(jobEnv({ experiment: "exp", worker: { is_active: 1, model_name: "pioreactor_40ml", model_version: "1.5" } })).toEqual({
      EXPERIMENT: "exp",
      JOB_SOURCE: "user",
      ACTIVE: "1",
    });
    expect(jobEnv({ experiment: "exp", worker: undefined })).toEqual({ EXPERIMENT: "exp", JOB_SOURCE: "user" });
  });
});

describe("kiosk roles", () => {
  it("tells standalone units, leaders, workers and unjoined units apart", () => {
    expect(roleOf({ leaderHostname: "pio1", isLeader: true, otherUnits: 0 })).toBe("standalone");
    expect(roleOf({ leaderHostname: "pio1", isLeader: true, otherUnits: 2 })).toBe("leader");
    expect(roleOf({ leaderHostname: "pio1", isLeader: false, otherUnits: 0 })).toBe("worker");
    expect(roleOf({ leaderHostname: null, isLeader: false, otherUnits: 0 })).toBe("unjoined");
  });

  it("reads the retained assignment message", () => {
    expect(parseAssignment('{"pioreactor_unit": "pio2", "experiment": "exp1"}')).toBe("exp1");
    expect(parseAssignment('{"pioreactor_unit": "pio2", "experiment": null}')).toBeNull();
    expect(parseAssignment("not json")).toBeUndefined();
  });

  it("validates names before asking the leader", () => {
    expect(validateExperimentName("current")).toMatch(/reserved/);
    expect(validateExperimentName("growth run 1")).toBeNull();
    expect(validateUnitName("pio2.local")).toMatch(/hostname/);
    expect(validateUnitName("pio-2")).toBeNull();
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

describe("kiosk onboarding (mocked backend)", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    window.localStorage.clear();
  });
  afterEach(() => jest.useRealTimers());

  const settle = async (promise) => {
    await jest.runAllTimersAsync();
    return promise;
  };

  it("stays done once finished, until reset", async () => {
    expect((await settle(getOnboarding())).done).toBe(false);
    await settle(finishOnboarding());
    expect((await settle(getOnboarding())).done).toBe(true);
    await settle(resetOnboarding());
    expect((await settle(getOnboarding())).done).toBe(false);
  });

  it("fails to join Wi-Fi with the test wrong password", async () => {
    const failing = connectWifi("LabNet", "wrongpassword");
    const assertion = expect(failing).rejects.toThrow("Incorrect password for LabNet.");
    await jest.runAllTimersAsync();
    await assertion;
    await expect(settle(connectWifi("LabNet", "secret123"))).resolves.toEqual({ connected: true, ssid: "LabNet" });
  });

  it("lists built-in models off the leader", async () => {
    await expect(settle(listModels({ isLeader: false }))).resolves.toEqual(MOCK_MODELS);
  });
});
