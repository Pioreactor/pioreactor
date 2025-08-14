import React, { createContext, useState, useContext, useEffect, useMemo, useCallback } from 'react';

const ExperimentContext = createContext();

export const useExperiment = () => useContext(ExperimentContext);

export const ExperimentProvider = ({ children }) => {
  const [experimentMetadata, setExperimentMetadata] = useState({});
  const [allExperiments, setAllExperiments] = useState([]);

  useEffect(() => {
    const getExperimentMetadata = async () => {
      const now = Date.now();
      let maybeExperimentMetadata = JSON.parse(window.localStorage.getItem("experimentMetadata"));

      // Check if we have metadata and if it is less than an hour old
      if (maybeExperimentMetadata && (now - maybeExperimentMetadata._createdAt < 60 * 60 * 1000)) {

        return maybeExperimentMetadata;
      }

      // Determine the initial URL to fetch metadata
      const primaryUrl = maybeExperimentMetadata?.experiment
        ? `/api/experiments/${maybeExperimentMetadata.experiment}`
        : "/api/experiments/latest";

      let data;

      try {
        // Try fetching the primary URL
        let response = await fetch(primaryUrl);

        if (!response.ok) {
          // If primary URL fails, throw an error to trigger fallback
          throw new Error(`Primary request failed with status: ${response.status} ${response.statusText}`);
        }

        data = await response.json();
      } catch (error) {
        console.warn("Primary request failed, attempting fallback:", error);

        try {
          // Fallback to /api/experiments/latest
          const fallbackResponse = await fetch("/api/experiments/latest");

          if (!fallbackResponse.ok) {
            throw new Error(`Fallback request also failed with status: ${fallbackResponse.status} ${fallbackResponse.statusText}`);
          }

          data = await fallbackResponse.json();
        } catch (fallbackError) {
          console.error("Both primary and fallback requests failed:", fallbackError);
          throw fallbackError; // Rethrow to allow higher-level error handling
        }
      }

      // Add the current timestamp to the data
      data._createdAt = now;
      window.localStorage.setItem("experimentMetadata", JSON.stringify(data));

      return data;
    };


    // Async function to update state
    const fetchAndSetMetadata = async () => {
      const metadata = await getExperimentMetadata();
      setExperimentMetadata(metadata);
    };

    fetchAndSetMetadata(); // Call the async function

  }, []);

  useEffect(() => {
    // Fetch all experiment metadata from the backend
    fetch("/api/experiments")
      .then((response) => response.json())
      .then((data) => {
        setAllExperiments(data);
      });
  }, []);

  const selectExperiment = useCallback((newName) => {
    const idx = allExperiments.findIndex(e => e.experiment === newName);
    if (idx < 0) return;
    const exp = { ...allExperiments[idx], _createdAt: Date.now() };
    setExperimentMetadata(exp);
    window.localStorage.setItem("experimentMetadata", JSON.stringify(exp));
  }, [allExperiments]);

  const updateExperiment = useCallback((newExp, put = false) => {
    const exp = { ...newExp, _createdAt: Date.now() };
    setExperimentMetadata(exp);
    window.localStorage.setItem("experimentMetadata", JSON.stringify(exp));

    if (put) {
      setAllExperiments(prev => [exp, ...prev]);
    } else {
      setAllExperiments(prev => {
        const updated = [...prev];
        const i = updated.findIndex(e => e.experiment === exp.experiment);
        if (i >= 0) updated[i] = exp;
        return updated;
      });
    }
  }, []);

  const contextValue = useMemo(() => ({
    experimentMetadata,
    allExperiments,
    selectExperiment,
    updateExperiment,
    // you almost never need to expose setAllExperiments directly
  }), [
    experimentMetadata,
    allExperiments,
    selectExperiment,
    updateExperiment
  ]);

  return (
    <ExperimentContext.Provider value={contextValue}>
      {children}
    </ExperimentContext.Provider>
  );
};
