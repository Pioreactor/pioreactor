import React, { createContext, useState, useContext, useEffect } from 'react';

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

  const selectExperiment = (newExperimentName) => {
    const foundExperiment = allExperiments.findIndex(exp => exp.experiment === newExperimentName);
    if (foundExperiment < 0){
      return
    }
    setExperimentMetadata(allExperiments[foundExperiment])
    window.localStorage.setItem("experimentMetadata", JSON.stringify(allExperiments[foundExperiment]))
  }

  const updateExperiment = (newExperimentObject, put=false) => {
    const now = Date.now()
    newExperimentObject._createdAt = now

    setExperimentMetadata(newExperimentObject);


    if (newExperimentObject){
      window.localStorage.setItem("experimentMetadata", JSON.stringify(newExperimentObject))
    }

    if (put){
      // PUT
      setAllExperiments((prevExperiment) => [newExperimentObject, ...prevExperiment])
    } else {
      // PATCH
      setAllExperiments((prevExperiments) => {
        const updatedExperiments = [...prevExperiments];
        const index = updatedExperiments.findIndex(exp => exp.experiment === newExperimentObject.experiment);
        updatedExperiments[index] = newExperimentObject;
        return updatedExperiments;
      });
    }

  };

  return (
    <ExperimentContext.Provider value={{ experimentMetadata, updateExperiment, allExperiments, setAllExperiments, selectExperiment}}>
      {children}
    </ExperimentContext.Provider>
  );
};