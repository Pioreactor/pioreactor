const BIOREACTOR_CONFIG_KEYS = {
  current_volume_ml: "initial_volume_ml",
  efflux_tube_volume_ml: "efflux_tube_volume_ml",
  alt_media_fraction: "initial_alt_media_fraction",
};

let bioreactorDescriptorsRequestCache = null;

export function parseNumericValue(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getBioreactorFallbackValue(config, key) {
  const configKey = BIOREACTOR_CONFIG_KEYS[key];
  const parsedConfigValue = parseNumericValue(config?.bioreactor?.[configKey]);
  if (parsedConfigValue !== null) {
    return parsedConfigValue;
  }

  if (key === "alt_media_fraction") {
    return 0;
  }

  return 14;
}

export function getBioreactorConfirmedValue(values, config, key) {
  return parseNumericValue(values?.[key]) ?? getBioreactorFallbackValue(config, key);
}

export function getBioreactorSubscriptionTopics(unit, experiment) {
  const baseTopics = [
    `pioreactor/${unit}/${experiment}/bioreactor/current_volume_ml`,
    `pioreactor/${unit}/${experiment}/bioreactor/efflux_tube_volume_ml`,
    `pioreactor/${unit}/${experiment}/bioreactor/alt_media_fraction`,
  ];

  return [
    ...baseTopics,
    ...baseTopics.map((topic) => topic.replace(`/${experiment}/`, `/_testing_${experiment}/`)),
  ];
}

export function resetBioreactorDescriptorsCache() {
  bioreactorDescriptorsRequestCache = null;
}

export async function getBioreactorDescriptors() {
  if (!bioreactorDescriptorsRequestCache) {
    bioreactorDescriptorsRequestCache = fetch("/api/bioreactor/descriptors")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP error! Status: ${response.status}`);
        }
        return response.json();
      })
      .catch((error) => {
        bioreactorDescriptorsRequestCache = null;
        throw error;
      });
  }

  return bioreactorDescriptorsRequestCache;
}

export async function updateBioreactorValues(unit, experiment, values) {
  const response = await fetch(`/api/workers/${unit}/bioreactor/update/experiments/${experiment}`, {
    method: "PATCH",
    body: JSON.stringify({ values }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return response.json();
  }

  let message = `Error ${response.status}.`;
  try {
    const payload = await response.json();
    if (payload?.error) {
      message = payload.error;
    }
  } catch (_error) {
    // ignore JSON parse errors and keep the default message
  }
  throw new Error(message);
}
