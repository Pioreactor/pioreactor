let workerJobDescriptorsRequestCache = new Map();
let settingsDescriptorsRequestCache = null;
let workerSettingsDescriptorsRequestCache = new Map();
let workerAutomationDescriptorsRequestCache = new Map();

function getAutomationCacheKey(unit, automationType) {
  return `${unit || ""}:${automationType}`;
}

export function resetWorkerJobDescriptorsCache() {
  workerJobDescriptorsRequestCache = new Map();
  settingsDescriptorsRequestCache = null;
  workerSettingsDescriptorsRequestCache = new Map();
  workerAutomationDescriptorsRequestCache = new Map();
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

export function buildSettingsCollectionsFromDescriptors(
  descriptors,
  { existingCollections = null } = {},
) {
  const collections = { ...(existingCollections || {}) };

  for (const collection of descriptors || []) {
    const existingCollection = collections[collection.key];
    const metadata = {
      state: existingCollection?.state ?? null,
      publishedSettings: {},
      metadata: {
        display_name: collection.display_name,
        subtext: collection.subtext,
        display: collection.display,
        description: collection.description,
        key: collection.key,
        source: collection.source,
      },
    };

    for (const field of collection.published_settings) {
      const existingSetting = existingCollection?.publishedSettings?.[field.key];
      metadata.publishedSettings[field.key] = {
        value: existingSetting?.value ?? field.default ?? null,
        label: field.label,
        type: field.type,
        unit: field.unit || null,
        display: field.display,
        description: field.description,
        editable: field.editable ?? true,
        min: field.min ?? null,
        max: field.max ?? null,
      };
    }

    collections[collection.key] = metadata;
  }

  return collections;
}

export function updatePublishedSettingValue(collections, collectionKey, settingKey, value) {
  const collection = collections[collectionKey];
  const existingSetting = collection?.publishedSettings?.[settingKey];
  if (!existingSetting) {
    return collections;
  }

  return {
    ...collections,
    [collectionKey]: {
      ...collection,
      publishedSettings: {
        ...collection.publishedSettings,
        [settingKey]: { ...existingSetting, value },
      },
    },
  };
}

export function getPublishedSettingsSignature(
  collections,
  { excludeKeys = [], separator = "\u0000" } = {},
) {
  const excludedKeys = new Set(excludeKeys);

  return Object.entries(collections)
    .filter(([key]) => !excludedKeys.has(key))
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, collection]) => {
      const settingKeys = Object.keys(collection.publishedSettings || {}).sort();
      return `${key}=${settingKeys.join(",")}`;
    })
    .join(separator);
}

export function getPublishedSettingsTopicsFromSignature(
  signature,
  { unit, experiment, includeState = false, separator = "\u0000" },
) {
  if (!experiment || !signature) {
    return [];
  }

  const topics = [];
  for (const collectionDescriptor of signature.split(separator)) {
    const [collectionName, settings = ""] = collectionDescriptor.split("=");
    if (!collectionName) {
      continue;
    }

    if (includeState) {
      topics.push(["pioreactor", unit, experiment, collectionName, "$state"].join("/"));
    }

    if (!settings) {
      continue;
    }

    for (const setting of settings.split(",")) {
      topics.push(["pioreactor", unit, experiment, collectionName, setting].join("/"));
    }
  }

  return topics;
}

async function createApiErrorFromResponse(response) {
  let errorMessage = `Error ${response.status}.`;

  try {
    const errorData = await response.json();
    errorMessage = errorData?.cause || errorData?.error || errorMessage;
  } catch (_error) {
    // Ignore malformed or empty error bodies and keep the HTTP status fallback.
  }

  return new Error(errorMessage);
}

export async function getWorkerJobDescriptors(unit) {
  if (!unit) {
    return [];
  }

  if (!workerJobDescriptorsRequestCache.has(unit)) {
    const pendingRequest = fetch(`/api/workers/${unit}/jobs/descriptors`)
      .then(async (response) => {
        if (!response.ok) {
          throw await createApiErrorFromResponse(response);
        }
        return response.json();
      })
      .then((descriptors) => {
        const resolvedDescriptors = Promise.resolve(descriptors);
        workerJobDescriptorsRequestCache.set(unit, resolvedDescriptors);
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

export async function getWorkerSettingsDescriptors(unit) {
  if (!unit) {
    return [];
  }

  if (!workerSettingsDescriptorsRequestCache.has(unit)) {
    const pendingRequest = fetch(`/api/workers/${unit}/settings/descriptors`)
      .then(async (response) => {
        if (!response.ok) {
          throw await createApiErrorFromResponse(response);
        }
        return response.json();
      })
      .then((descriptors) => {
        const resolvedDescriptors = Promise.resolve(descriptors);
        workerSettingsDescriptorsRequestCache.set(unit, resolvedDescriptors);
        return descriptors;
      })
      .catch((error) => {
        workerSettingsDescriptorsRequestCache.delete(unit);
        throw error;
      });

    workerSettingsDescriptorsRequestCache.set(unit, pendingRequest);
  }

  return workerSettingsDescriptorsRequestCache.get(unit);
}

export async function getSettingsDescriptors() {
  if (!settingsDescriptorsRequestCache) {
    settingsDescriptorsRequestCache = fetch("/api/settings/descriptors")
      .then(async (response) => {
        if (!response.ok) {
          throw await createApiErrorFromResponse(response);
        }
        return response.json();
      })
      .catch((error) => {
        settingsDescriptorsRequestCache = null;
        throw error;
      });
  }

  return settingsDescriptorsRequestCache;
}

export async function getAutomationDescriptors(unit, automationType) {
  if (!automationType) {
    return [];
  }

  const isWorkerScoped = Boolean(unit && unit !== "$broadcast");
  const cacheKey = getAutomationCacheKey(isWorkerScoped ? unit : "$leader", automationType);

  if (!workerAutomationDescriptorsRequestCache.has(cacheKey)) {
    const endpoint = isWorkerScoped
      ? `/api/workers/${unit}/automations/descriptors/${automationType}`
      : `/api/automations/descriptors/${automationType}`;

    const pendingRequest = fetch(endpoint)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Error ${response.status}.`);
        }
        return response.json();
      })
      .then((descriptors) => {
        const resolvedDescriptors = Promise.resolve(descriptors);
        workerAutomationDescriptorsRequestCache.set(cacheKey, resolvedDescriptors);
        return descriptors;
      })
      .catch((error) => {
        workerAutomationDescriptorsRequestCache.delete(cacheKey);
        throw error;
      });

    workerAutomationDescriptorsRequestCache.set(cacheKey, pendingRequest);
  }

  return workerAutomationDescriptorsRequestCache.get(cacheKey);
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
