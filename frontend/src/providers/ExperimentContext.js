import React, { createContext, useState, useContext, useEffect, useMemo, useCallback } from 'react';

const ExperimentContext = createContext();

export const useExperiment = () => useContext(ExperimentContext);

const EXPERIMENT_METADATA_KEY = "experimentMetadata";
const METADATA_TTL_MS = 60 * 60 * 1000;

const readCachedExperimentMetadata = () => {
  const cachedValue = window.localStorage.getItem(EXPERIMENT_METADATA_KEY);
  if (!cachedValue) return null;

  try {
    const parsed = JSON.parse(cachedValue);
    if (!parsed || typeof parsed !== "object") return null;

    const createdAt = Number.isFinite(parsed._createdAt) ? parsed._createdAt : 0;
    return { ...parsed, _createdAt: createdAt };
  } catch (error) {
    window.localStorage.removeItem(EXPERIMENT_METADATA_KEY);
    return null;
  }
};

const writeCachedExperimentMetadata = (metadata) => {
  try {
    window.localStorage.setItem(EXPERIMENT_METADATA_KEY, JSON.stringify(metadata));
  } catch (error) {
    console.warn("Failed to persist experiment metadata:", error);
  }
};

const fetchJson = async (url, signal) => {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`Request failed with status: ${response.status} ${response.statusText}`);
  }
  return response.json();
};

export const ExperimentProvider = ({ children }) => {
  const [experimentMetadata, setExperimentMetadata] = useState({});
  const [allExperiments, setAllExperiments] = useState([]);

  useEffect(() => {
    const controller = new AbortController();
    let isActive = true;

    const getExperimentMetadata = async () => {
      const now = Date.now();
      const maybeExperimentMetadata = readCachedExperimentMetadata();

      // Check if we have metadata and if it is less than an hour old
      if (maybeExperimentMetadata && (now - maybeExperimentMetadata._createdAt < METADATA_TTL_MS)) {
        return maybeExperimentMetadata;
      }

      // Determine the initial URL to fetch metadata
      const primaryUrl = maybeExperimentMetadata?.experiment
        ? `/api/experiments/${encodeURIComponent(maybeExperimentMetadata.experiment)}`
        : "/api/experiments/latest";

      try {
        // Try fetching the primary URL
        const data = await fetchJson(primaryUrl, controller.signal);
        const enrichedData = { ...data, _createdAt: now };
        writeCachedExperimentMetadata(enrichedData);
        return enrichedData;
      } catch (error) {
        if (controller.signal.aborted) {
          throw error;
        }
        console.warn("Primary request failed, attempting fallback:", error);

        if (primaryUrl === "/api/experiments/latest") {
          throw error;
        }
        // Fallback to /api/experiments/latest
        const fallbackData = await fetchJson("/api/experiments/latest", controller.signal);
        const enrichedData = { ...fallbackData, _createdAt: now };
        writeCachedExperimentMetadata(enrichedData);
        return enrichedData;
      }
    };


    // Async function to update state
    const fetchAndSetMetadata = async () => {
      try {
        const metadata = await getExperimentMetadata();
        if (!isActive) return;
        setExperimentMetadata(metadata);
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Failed to load experiment metadata:", error);
      }
    };

    fetchAndSetMetadata(); // Call the async function

    return () => {
      isActive = false;
      controller.abort();
    };
  }, []);

  useEffect(() => {
    // Fetch all experiment metadata from the backend
    const controller = new AbortController();

    const fetchAllExperiments = async () => {
      try {
        const data = await fetchJson("/api/experiments", controller.signal);
        setAllExperiments(data);
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Failed to load experiments:", error);
      }
    };

    fetchAllExperiments();

    return () => {
      controller.abort();
    };
  }, []);

  const selectExperiment = useCallback((newName) => {
    const idx = allExperiments.findIndex(e => e.experiment === newName);
    if (idx < 0) return;
    const exp = { ...allExperiments[idx], _createdAt: Date.now() };
    setExperimentMetadata(exp);
    writeCachedExperimentMetadata(exp);
  }, [allExperiments]);

  const updateExperiment = useCallback((newExp, put = false) => {
    if (!newExp) return;
    const exp = { ...newExp, _createdAt: Date.now() };
    setExperimentMetadata(exp);
    writeCachedExperimentMetadata(exp);

    setAllExperiments(prev => {
      const i = prev.findIndex(e => e.experiment === exp.experiment);
      if (i < 0) {
        return put ? [exp, ...prev] : [...prev, exp];
      }
      if (put) {
        return [exp, ...prev.filter(e => e.experiment !== exp.experiment)];
      }
      const updated = [...prev];
      updated[i] = exp;
      return updated;
    });
  }, []);

  const contextValue = useMemo(() => ({
    experimentMetadata,
    allExperiments,
    selectExperiment,
    updateExperiment,
    setAllExperiments,
    // you almost never need to expose setAllExperiments directly
  }), [
    experimentMetadata,
    allExperiments,
    selectExperiment,
    updateExperiment,
    setAllExperiments
  ]);

  return (
    <ExperimentContext.Provider value={contextValue}>
      {children}
    </ExperimentContext.Provider>
  );
};
