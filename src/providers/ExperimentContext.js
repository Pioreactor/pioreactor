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

      // Fetch new metadata if we don't have any or if it's too old
      const url = maybeExperimentMetadata?.experiment
        ? `/api/experiments/${maybeExperimentMetadata.experiment}`
        : "/api/experiments/latest";

      const response = await fetch(url);
      const data = await response.json();

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

  const updateExperiment = (newExperiment, put=false) => {
    const now = Date.now()
    newExperiment._createdAt = now

    setExperimentMetadata(newExperiment);


    if (newExperiment){
      window.localStorage.setItem("experimentMetadata", JSON.stringify(newExperiment))
    }

    if (put){
      // PUT
      setAllExperiments((prevExperiment) => [newExperiment, ...prevExperiment])
    } else {
      // PATCH
      setAllExperiments((prevExperiments) => {
        const updatedExperiments = [...prevExperiments];
        const index = updatedExperiments.findIndex(exp => exp.experiment === newExperiment.experiment);
        updatedExperiments[index] = newExperiment;
        return updatedExperiments;
      });
    }

  };

  return (
    <ExperimentContext.Provider value={{ experimentMetadata, updateExperiment, allExperiments, setAllExperiments}}>
      {children}
    </ExperimentContext.Provider>
  );
};