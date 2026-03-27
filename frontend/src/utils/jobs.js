let workerJobDescriptorsCache = new Map();
let workerJobDescriptorsRequestCache = new Map();

export function resetWorkerJobDescriptorsCache() {
  workerJobDescriptorsCache = new Map();
  workerJobDescriptorsRequestCache = new Map();
}

export function createMonitorJobState() {
  return {
    state: null,
    metadata: { display: false },
    publishedSettings: {
      versions: {
        value: null, label: null, type: "json", unit: null, display: false, description: null, editable: false,
      },
      voltage_on_pwm_rail: {
        value: null, label: null, type: "json", unit: null, display: false, description: null, editable: false,
      },
      ipv4: {
        value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
      },
      wlan_mac_address: {
        value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
      },
      eth_mac_address: {
        value: null, label: null, type: "string", unit: null, display: false, description: null, editable: false,
      },
    },
  };
}

export function buildJobsStateFromDescriptors(
  descriptors,
  { includeMonitor = false, initialState = "disconnected", existingJobs = null } = {},
) {
  const jobs = { ...(existingJobs || {}) };

  if (includeMonitor && !jobs.monitor) {
    jobs.monitor = createMonitorJobState();
  }

  for (const job of descriptors || []) {
    const existingJob = jobs[job.job_name];
    const metaData = {
      state: existingJob?.state ?? initialState,
      publishedSettings: {},
      metadata: {
        display_name: job.display_name,
        subtext: job.subtext,
        display: job.display,
        description: job.description,
        key: job.job_name,
        source: job.source,
      },
    };

    for (const field of job.published_settings) {
      const existingSetting = existingJob?.publishedSettings?.[field.key];
      metaData.publishedSettings[field.key] = {
        value: existingSetting?.value ?? field.default ?? null,
        label: field.label,
        type: field.type,
        unit: field.unit || null,
        display: field.display,
        description: field.description,
        editable: field.editable ?? true,
      };
    }

    jobs[job.job_name] = metaData;
  }

  return jobs;
}

export async function getWorkerJobDescriptors(unit) {
  if (!unit) {
    return [];
  }

  if (workerJobDescriptorsCache.has(unit)) {
    return workerJobDescriptorsCache.get(unit);
  }

  if (!workerJobDescriptorsRequestCache.has(unit)) {
    const pendingRequest = fetch(`/api/workers/${unit}/jobs/descriptors`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Error ${response.status}.`);
        }
        return response.json();
      })
      .then((descriptors) => {
        workerJobDescriptorsCache.set(unit, descriptors);
        workerJobDescriptorsRequestCache.delete(unit);
        return descriptors;
      })
      .catch((error) => {
        workerJobDescriptorsRequestCache.delete(unit);
        throw error;
      });

    workerJobDescriptorsRequestCache.set(unit, pendingRequest);
  }

  return workerJobDescriptorsRequestCache.get(unit);
}

export function runPioreactorJob(
  unit,
  experiment,
  job,
  args = [],
  options = {},
  configOverrides = [],
) {
  return fetch(`/api/workers/${unit}/jobs/run/job_name/${job}/experiments/${experiment}`, {
    method: "PATCH",
    body: JSON.stringify({
      args,
      options,
      env: { EXPERIMENT: experiment, JOB_SOURCE: "user" },
      config_overrides: configOverrides,
    }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  })
    .then((response) => {
      if (response.ok) {
        return;
      }
      throw new Error(`Error ${response.status}.`);
    })
    .catch((error) => {
      throw error;
    });
}

export function runPioreactorJobViaUnitAPI(job, args = [], options = {}) {
  return fetch(`/unit_api/jobs/run/job_name/${job}`, {
    method: "PATCH",
    body: JSON.stringify({ args, options }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  })
    .then((response) => {
      if (response.ok) {
        return;
      }
      throw new Error(`Error ${response.status}.`);
    })
    .catch((error) => {
      throw error;
    });
}
