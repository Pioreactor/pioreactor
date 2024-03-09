import React, { createContext, useState, useContext, useEffect } from 'react';

const ExperimentContext = createContext();

export const useExperiment = () => useContext(ExperimentContext);

export const ExperimentProvider = ({ children }) => {
  const [experimentMetadata, setExperimentMetadata] = useState({});

  useEffect(() => {
    // Fetch the latest experiment metadata from the backend
    fetch("/api/experiments/latest")
      .then((response) => response.json())
      .then((data) => {
        setExperimentMetadata(data);
      });
  }, []);

  const updateExperiment = (newExperiment) => {
    setExperimentMetadata(newExperiment);
  };

  return (
    <ExperimentContext.Provider value={{ experimentMetadata, updateExperiment }}>
      {children}
    </ExperimentContext.Provider>
  );
};