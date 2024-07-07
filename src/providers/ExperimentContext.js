import React, { createContext, useState, useContext, useEffect } from 'react';

const ExperimentContext = createContext();

export const useExperiment = () => useContext(ExperimentContext);

export const ExperimentProvider = ({ children }) => {
  const [experimentMetadata, setExperimentMetadata] = useState({});
  const [allExperiments, setAllExperiments] = useState([]);

  useEffect(() => {
    // defer to disk
    const maybeExperimentMetadata = JSON.parse(window.localStorage.getItem("experimentMetadata"))

    if (maybeExperimentMetadata){
      setExperimentMetadata(maybeExperimentMetadata)
    }
    // Fetch the latest experiment metadata from the backend
    else {
      fetch("/api/experiments/latest")
        .then((response) => response.json())
        .then((data) => {
          setExperimentMetadata(data);
          window.localStorage.setItem("experimentMetadata", JSON.stringify(data));
        });
    }

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