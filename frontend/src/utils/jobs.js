let workerJobDescriptorsRequestCache = new Map();
let settingsDescriptorsRequestCache = null;
let workerSettingsDescriptorsRequestCache = new Map();
let workerAutomationDescriptorsRequestCache = new Map();

function getAutomationCacheKey(unit, automationType) {
  return `${unit || ""}:${automationType}`;
}

function buildPublishedSetting(field, existingSetting, { includeLimits = false } = {}) {
  const publishedSetting = {
    value: existingSetting?.value ?? field.default ?? null,
    label: field.label,
    type: field.type,
    unit: field.unit || null,
    display: field.display,
    description: field.description,
    editable: field.editable ?? true,
  };

  if (includeLimits) {
    publishedSetting.min = field.min ?? null;
    publishedSetting.max = field.max ?? null;
  }

  return publishedSetting;
}

function requestJson(endpoint, { createError = createApiErrorFromResponse } = {}) {
  return fetch(endpoint).then(async (response) => {
    if (!response.ok) {
      throw await createError(response);
    }
    return response.json();
  });
}

function getCachedJson(cache, cacheKey, endpoint, options = {}) {
  if (!cache.has(cacheKey)) {
    const pendingRequest = requestJson(endpoint, options)
      .then((descriptors) => {
        const resolvedDescriptors = Promise.resolve(descriptors);
        cache.set(cacheKey, resolvedDescriptors);
        return descriptors;
      })
      .catch((error) => {
        cache.delete(cacheKey);
        throw error;
      });

    cache.set(cacheKey, pendingRequest);
  }

  return cache.get(cacheKey);
}

function runJobPatch(endpoint, body) {
  return fetch(endpoint, {
    method: "PATCH",
    body: JSON.stringify(body),
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
      metaData.publishedSettings[field.key] = buildPublishedSetting(field, existingSetting);
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
      metadata.publishedSettings[field.key] = buildPublishedSetting(
        field,
        existingSetting,
        { includeLimits: true },
      );
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

  return getCachedJson(
    workerJobDescriptorsRequestCache,
    unit,
    `/api/workers/${unit}/jobs/descriptors`,
  );
}

export async function getWorkerSettingsDescriptors(unit) {
  if (!unit) {
    return [];
  }

  return getCachedJson(
    workerSettingsDescriptorsRequestCache,
    unit,
    `/api/workers/${unit}/settings/descriptors`,
  );
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

  const endpoint = isWorkerScoped
    ? `/api/workers/${unit}/automations/descriptors/${automationType}`
    : `/api/automations/descriptors/${automationType}`;

  return getCachedJson(workerAutomationDescriptorsRequestCache, cacheKey, endpoint, {
    createError: (response) => new Error(`Error ${response.status}.`),
  });
}

export function runPioreactorJob(
  unit,
  experiment,
  job,
  args = [],
  options = {},
  configOverrides = [],
) {
  return runJobPatch(
    `/api/workers/${unit}/jobs/run/job_name/${job}/experiments/${experiment}`,
    {
      args,
      options,
      env: { EXPERIMENT: experiment, JOB_SOURCE: "user" },
      config_overrides: configOverrides,
    },
  );
}

export function runPioreactorJobViaUnitAPI(job, args = [], options = {}) {
  return runJobPatch(`/unit_api/jobs/run/job_name/${job}`, { args, options });
}
