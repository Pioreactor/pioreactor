// RunningProfilesContext.js

import React from 'react';
import {runPioreactorJobViaUnitAPI} from "../utils/jobs"


// Create the context
const RunningProfilesContext = React.createContext(null);

// Export a custom hook for consuming the context
export function useRunningProfiles() {
  return React.useContext(RunningProfilesContext);
}

// Create a provider component
export function RunningProfilesProvider({ children, experiment }) {
  const [runningProfiles, setRunningProfiles] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(false);
  const fetchRequestId = React.useRef(0);

  // Use a callback for fetching the running profiles
  const fetchRunningProfiles = React.useCallback(async () => {
    const requestId = ++fetchRequestId.current;
    setError(false);
    // If we don't yet know the experiment, don't hit the API.
    if (!experiment) {
      setRunningProfiles([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `/api/experiments/${encodeURIComponent(experiment)}/experiment_profiles/running`
      );
      if (!response.ok) {
        throw new Error(`Failed to fetch running profiles: ${response.statusText}`);
      }
      const data = await response.json();
      if (requestId === fetchRequestId.current) setRunningProfiles(data);
    } catch (error) {
      if (requestId === fetchRequestId.current) setError(true);
    } finally {
      if (requestId === fetchRequestId.current) setLoading(false);
    }
  }, [experiment]);

  // Fetch running profiles once on mount, and whenever `experiment` changes
  React.useEffect(() => {
    setRunningProfiles([]);
    fetchRunningProfiles();
    return () => {
      fetchRequestId.current += 1;
    };
  }, [fetchRunningProfiles]);

  // Helper to re-fetch
  const refreshRunningProfiles = React.useCallback(() => {
    fetchRunningProfiles();
  }, [fetchRunningProfiles]);

  // Stop a profile
  const stopProfile = React.useCallback(
    async (job_id) => {
      try {
        const response = await fetch(`/unit_api/jobs/stop`, {
          method: 'POST',
          body: JSON.stringify({ job_id: job_id }),
          headers: {
            Accept: 'application/json',
            'Content-Type': 'application/json'
          }
        });
        if (!response.ok) {
          throw new Error('Failed to stop the profile.');
        }

        // Artificial delay. Wait 2 seconds before refreshing:
        setLoading(true)
        setTimeout(() => {
          refreshRunningProfiles();
        }, 3000);
      } catch (error) {
        console.error('Error stopping profile:', error);
        throw error;
      }
    },
    [refreshRunningProfiles]
  );

  // Start a profile (or run a job) — for example:
  const startProfile = React.useCallback(
    async (selectedExperimentProfile, experiment, dryRun = false) => {
      try {
        const params = dryRun ? { 'dry-run': null } : {};
        await runPioreactorJobViaUnitAPI(
          'experiment_profile',
          ['execute', selectedExperimentProfile, experiment],
          params
        );
        // Artificial delay. Wait N seconds before refreshing:
        setLoading(true);
        setTimeout(() => {
          refreshRunningProfiles();
        }, 3000);
      } catch (error) {
        console.error('Error starting profile:', error);
        throw error;
      }
    },
    [refreshRunningProfiles]
  );

  // The value exposed by the context
  const value = {
    runningProfiles,
    loading,
    error,
    stopProfile,
    startProfile,
    refreshRunningProfiles
  };

  return (
    <RunningProfilesContext.Provider value={value}>
      {children}
    </RunningProfilesContext.Provider>
  );
}
