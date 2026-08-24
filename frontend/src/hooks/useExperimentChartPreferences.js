import React from "react";


const PREFERENCE_FIELDS = {
  overview: "overview_chart_keys",
  pioreactor: "pioreactor_chart_keys",
};


async function getResponsePayload(response, fallbackMessage) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || fallbackMessage);
  }
  return payload;
}


export default function useExperimentChartPreferences({ chartPage, config, configReady, experiment }) {
  const preferenceField = PREFERENCE_FIELDS[chartPage];
  const requestVersionRef = React.useRef(0);
  const [resource, setResource] = React.useState({
    experiment: null,
    descriptors: [],
    preferences: null,
    error: null,
  });
  const [isLoading, setIsLoading] = React.useState(Boolean(experiment));

  if (!preferenceField) {
    throw new Error(`Unsupported chart page: ${chartPage}`);
  }

  const refresh = React.useCallback(async ({ signal } = {}) => {
    if (!experiment) {
      setIsLoading(false);
      return;
    }

    const requestVersion = requestVersionRef.current + 1;
    requestVersionRef.current = requestVersion;
    setIsLoading(true);

    try {
      const [descriptorsResponse, preferencesResponse] = await Promise.all([
        fetch("/api/charts/descriptors", { signal }),
        fetch(`/api/experiments/${encodeURIComponent(experiment)}/chart_preferences`, { signal }),
      ]);
      const [descriptors, preferences] = await Promise.all([
        getResponsePayload(descriptorsResponse, "Could not load the available charts."),
        getResponsePayload(preferencesResponse, "Could not load chart preferences."),
      ]);

      if (!signal?.aborted && requestVersion === requestVersionRef.current) {
        setResource({ experiment, descriptors, preferences, error: null });
      }
    } catch (error) {
      if (error.name !== "AbortError" && requestVersion === requestVersionRef.current) {
        setResource({ experiment, descriptors: [], preferences: null, error: error.message });
      }
    } finally {
      if (!signal?.aborted && requestVersion === requestVersionRef.current) {
        setIsLoading(false);
      }
    }
  }, [experiment]);

  React.useEffect(() => {
    if (!experiment) {
      setIsLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    void refresh({ signal: controller.signal });

    return () => controller.abort();
  }, [experiment, refresh]);

  const isCurrentExperiment = resource.experiment === experiment;
  const descriptors = isCurrentExperiment ? resource.descriptors : [];
  const preferences = isCurrentExperiment ? resource.preferences : null;
  const storedChartKeys = preferences?.[preferenceField] ?? null;
  const configuredDefaultChartKeys = Object.entries(config["ui.overview.charts"] || {})
    .filter(([, isEnabled]) => isEnabled === "1")
    .map(([chartKey]) => chartKey);
  const configuredDefaultChartKeySet = new Set(configuredDefaultChartKeys);
  const defaultChartKeys = descriptors
    .filter((descriptor) => configuredDefaultChartKeySet.has(descriptor.chart_key))
    .map((descriptor) => descriptor.chart_key);
  const requestedChartKeys = storedChartKeys === null ? defaultChartKeys : storedChartKeys;
  const availableChartKeySet = new Set(descriptors.map((descriptor) => descriptor.chart_key));
  const selectedChartKeys = requestedChartKeys.filter((chartKey) => availableChartKeySet.has(chartKey));

  const save = React.useCallback(async (chartKeys) => {
    const response = await fetch(
      `/api/experiments/${encodeURIComponent(experiment)}/chart_preferences`,
      {
        method: "PATCH",
        body: JSON.stringify({ [preferenceField]: chartKeys }),
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      },
    );
    const preferencesPayload = await getResponsePayload(
      response,
      "Could not save chart preferences. Please try again.",
    );
    setResource((currentResource) => (
      currentResource.experiment === experiment
        ? { ...currentResource, preferences: preferencesPayload, error: null }
        : currentResource
    ));
  }, [experiment, preferenceField]);

  return {
    defaultChartKeys,
    descriptors,
    error: isCurrentExperiment ? resource.error : null,
    isLoading: !isCurrentExperiment || isLoading || !configReady,
    isUsingDefaults: storedChartKeys === null,
    refresh,
    save,
    selectedChartKeys,
  };
}
