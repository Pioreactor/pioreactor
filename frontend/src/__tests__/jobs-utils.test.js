import {
  buildSettingsCollectionsFromDescriptors,
  buildJobsStateFromDescriptors,
  createMonitorJobState,
  getPublishedSettingsSignature,
  getPublishedSettingsTopicsFromSignature,
  getWorkerJobDescriptors,
  getWorkerSettingsDescriptors,
  resetWorkerJobDescriptorsCache,
  updatePublishedSettingValue,
} from "../utils/jobs";
import {
  canQuickEditCardSetting,
  getCardSettingDisplayKind,
} from "../components/pioreactorCardQuickControls";

describe("jobs utils", () => {
  beforeEach(() => {
    resetWorkerJobDescriptorsCache();
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("buildJobsStateFromDescriptors preserves false defaults and editable=false", () => {
    const jobs = buildJobsStateFromDescriptors(
      [
        {
          job_name: "worker_plugin",
          display_name: "Worker plugin",
          display: true,
          description: "From worker",
          source: "plugin",
          published_settings: [
            {
              key: "enabled",
              type: "boolean",
              display: true,
              default: false,
              editable: false,
              label: "Enabled",
              description: "Whether enabled",
            },
          ],
        },
      ],
      { includeMonitor: true },
    );

    expect(jobs.monitor).toEqual(createMonitorJobState());
    expect(jobs.worker_plugin.publishedSettings.enabled.value).toBe(false);
    expect(jobs.worker_plugin.publishedSettings.enabled.editable).toBe(false);
  });

  test("canQuickEditCardSetting uses descriptor editable metadata instead of labels", () => {
    expect(canQuickEditCardSetting({
      value: "{\"A\": 10}",
      label: "LED intensity",
      type: "string",
      editable: false,
    }, true)).toBe(false);

    expect(canQuickEditCardSetting({
      value: "12",
      label: "LED intensity",
      type: "numeric",
      editable: true,
    }, true)).toBe(true);
  });

  test("getCardSettingDisplayKind special-cases stable job setting identities", () => {
    expect(getCardSettingDisplayKind("leds", "intensity")).toBe("led_intensity");
    expect(getCardSettingDisplayKind("pwms", "dc")).toBe("pwm_dc");
    expect(getCardSettingDisplayKind("leds", "renamed_intensity")).toBe("default");
  });

  test("buildJobsStateFromDescriptors preserves existing monitor state when merging descriptors", () => {
    const jobs = buildJobsStateFromDescriptors(
      [
        {
          job_name: "worker_plugin",
          display_name: "Worker plugin",
          display: true,
          description: "From worker",
          source: "plugin",
          published_settings: [],
        },
      ],
      {
        includeMonitor: true,
        existingJobs: {
          monitor: {
            ...createMonitorJobState(),
            state: "ready",
            publishedSettings: {
              ...createMonitorJobState().publishedSettings,
              ipv4: {
                ...createMonitorJobState().publishedSettings.ipv4,
                value: "192.168.1.50",
              },
            },
          },
        },
      },
    );

    expect(jobs.monitor.state).toBe("ready");
    expect(jobs.monitor.publishedSettings.ipv4.value).toBe("192.168.1.50");
    expect(jobs.worker_plugin.state).toBe("disconnected");
  });

  test("buildJobsStateFromDescriptors supports nullable initial state for bulk controls", () => {
    const jobs = buildJobsStateFromDescriptors(
      [
        {
          job_name: "dosing_automation",
          display_name: "Dosing automation",
          display: true,
          description: "Bulk",
          source: "app",
          published_settings: [],
        },
      ],
      { initialState: null },
    );

    expect(jobs.dosing_automation.state).toBeNull();
  });

  test("buildSettingsCollectionsFromDescriptors builds passive settings collections", () => {
    const collections = buildSettingsCollectionsFromDescriptors(
      [
        {
          key: "leds",
          display_name: "LED settings",
          display: false,
          description: "Passive controls",
          source: "app",
          published_settings: [
            {
              key: "intensity",
              type: "string",
              display: true,
              default: "{\"A\": 0}",
              editable: false,
              label: "LED intensity",
              description: "LED output",
            },
          ],
        },
      ],
    );

    expect(collections.leds.metadata.key).toBe("leds");
    expect(collections.leds.metadata.display_name).toBe("LED settings");
    expect(collections.leds.state).toBeNull();
    expect(collections.leds.publishedSettings.intensity.value).toBe("{\"A\": 0}");
    expect(collections.leds.publishedSettings.intensity.editable).toBe(false);
  });

  test("updatePublishedSettingValue updates one setting without creating unknown settings", () => {
    const collections = buildSettingsCollectionsFromDescriptors([
      {
        key: "leds",
        display_name: "LED settings",
        display: false,
        published_settings: [
          {
            key: "intensity",
            type: "string",
            display: true,
            default: "{\"A\": 0}",
            label: "LED intensity",
          },
        ],
      },
    ]);

    const updated = updatePublishedSettingValue(collections, "leds", "intensity", "{\"A\": 20}");

    expect(updated.leds.publishedSettings.intensity.value).toBe("{\"A\": 20}");
    expect(updatePublishedSettingValue(collections, "leds", "missing", 1)).toBe(collections);
  });

  test("published settings signature builds stable MQTT topics", () => {
    const collections = buildJobsStateFromDescriptors([
      {
        job_name: "stirring",
        display_name: "Stirring",
        display: true,
        published_settings: [
          { key: "target_rpm", type: "numeric", display: true },
        ],
      },
    ], { includeMonitor: true });
    const signature = getPublishedSettingsSignature(collections, { excludeKeys: ["monitor"] });

    expect(getPublishedSettingsTopicsFromSignature(signature, {
      unit: "unit1",
      experiment: "exp1",
      includeState: true,
    })).toEqual([
      "pioreactor/unit1/exp1/stirring/$state",
      "pioreactor/unit1/exp1/stirring/target_rpm",
    ]);
  });

  test("getWorkerJobDescriptors caches per unit", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ job_name: "worker_plugin", published_settings: [] }]),
    });

    const first = await getWorkerJobDescriptors("unit1");
    const second = await getWorkerJobDescriptors("unit1");

    expect(first).toEqual([{ job_name: "worker_plugin", published_settings: [] }]);
    expect(second).toEqual(first);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit1/jobs/descriptors");
  });

  test("getWorkerSettingsDescriptors fetches worker settings descriptors", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve([{ key: "leds", published_settings: [] }]),
    });

    const descriptors = await getWorkerSettingsDescriptors("unit1");

    expect(descriptors).toEqual([{ key: "leds", published_settings: [] }]);
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit1/settings/descriptors");
  });

  test("getWorkerJobDescriptors surfaces API cause on failure", async () => {
    global.fetch.mockResolvedValue({
      ok: false,
      status: 502,
      json: () => Promise.resolve({
        error: "Fetching job descriptors failed on worker02.",
        cause: "Fetching job descriptors failed on worker02.",
      }),
    });

    await expect(getWorkerJobDescriptors("worker02")).rejects.toThrow(
      "Fetching job descriptors failed on worker02.",
    );
  });
});
