import React from "react";

import { getConfig } from "../utils/config";


let leaderHostnamePromise = null;

function fetchLeaderHostname() {
  if (leaderHostnamePromise === null) {
    let leaderHostname = null;
    leaderHostnamePromise = Promise.resolve(getConfig((config) => {
      leaderHostname = config["cluster.topology"]?.leader_hostname || null;
    })).then(() => {
      if (leaderHostname === null) {
        leaderHostnamePromise = null;
      }
      return leaderHostname;
    });
  }
  return leaderHostnamePromise;
}

// The leader's hostname, fetched once per page load and shared by every caller.
export default function useLeaderHostname() {
  const [leaderHostname, setLeaderHostname] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    fetchLeaderHostname().then((hostname) => {
      if (!cancelled) {
        setLeaderHostname(hostname);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return leaderHostname;
}
