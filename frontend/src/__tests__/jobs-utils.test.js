import {
  buildJobsStateFromDescriptors,
  createMonitorJobState,
  getWorkerJobDescriptors,
  resetWorkerJobDescriptorsCache,
} from "../utils/jobs";

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
});
