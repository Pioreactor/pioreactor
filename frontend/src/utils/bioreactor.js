const BIOREACTOR_CONFIG_KEYS = {
  current_volume_ml: "initial_volume_ml",
  efflux_tube_volume_ml: "efflux_tube_volume_ml",
  alt_media_fraction: "initial_alt_media_fraction",
  cumulative_media_added_ml: "initial_cumulative_media_added_ml",
  cumulative_alt_media_added_ml: "initial_cumulative_alt_media_added_ml",
  cumulative_waste_removed_ml: "initial_cumulative_waste_removed_ml",
};

const BIOREACTOR_FALLBACK_VALUES = {
  current_volume_ml: 14,
  efflux_tube_volume_ml: 14,
  alt_media_fraction: 0,
  cumulative_media_added_ml: 0,
  cumulative_alt_media_added_ml: 0,
  cumulative_waste_removed_ml: 0,
};

const DEFAULT_BIOREACTOR_SUBSCRIPTION_KEYS = Object.keys(BIOREACTOR_FALLBACK_VALUES);

export function parseNumericValue(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getBioreactorFallbackValue(config, key, descriptor = null) {
  const parsedDescriptorDefault = parseNumericValue(descriptor?.default);
  if (parsedDescriptorDefault !== null) {
    return parsedDescriptorDefault;
  }

  const configKey = BIOREACTOR_CONFIG_KEYS[key];
  const parsedConfigValue = parseNumericValue(config?.bioreactor?.[configKey]);
  if (parsedConfigValue !== null) {
    return parsedConfigValue;
  }

  return BIOREACTOR_FALLBACK_VALUES[key] ?? null;
}

export function getBioreactorConfirmedValue(values, config, descriptorOrKey) {
  const descriptor = typeof descriptorOrKey === "string" ? null : descriptorOrKey;
  const key = descriptor?.key ?? descriptorOrKey;
  return parseNumericValue(values?.[key]) ?? getBioreactorFallbackValue(config, key, descriptor);
}

export function getBioreactorSubscriptionTopics(unit, experiment, keys = DEFAULT_BIOREACTOR_SUBSCRIPTION_KEYS) {
  const uniqueKeys = Array.from(new Set(keys || [])).filter(Boolean);
  const baseTopics = uniqueKeys.map((key) => `pioreactor/${unit}/${experiment}/bioreactor/${key}`);

  return [
    ...baseTopics,
    ...baseTopics.map((topic) => topic.replace(`/${experiment}/`, `/_testing_${experiment}/`)),
  ];
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
