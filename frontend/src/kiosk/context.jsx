import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { enc, leaderApi, setLeaderOrigin, unitApi } from "./api";
import { createBroker } from "./mqtt";

export const KioskContext = createContext(null);
export const useKiosk = () => useContext(KioskContext);

const BOOT_RETRY_MS = 3000;

// The page is served by the Pioreactor it controls, so "self" is whoever answers
// /unit_api/health. Keep retrying: the screen can start before the web server.
function useBootInfo() {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    let cancelled = false;
    let timer;
    const load = async () => {
      try {
        const [health, config] = await Promise.all([unitApi("/health"), unitApi("/config/merged")]);
        if (!cancelled) setInfo({ unit: health.pioreactor_unit, config });
      } catch (_error) {
        if (!cancelled) timer = setTimeout(load, BOOT_RETRY_MS);
      }
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return info;
}

function leaderOriginFor(unit, config) {
  const topology = config["cluster.topology"] || {};
  if (!topology.leader_address || unit === topology.leader_hostname) return "";
  return `${window.location.protocol}//${topology.leader_address}`;
}

function parseAssignment(payload) {
  try {
    const parsed = JSON.parse(payload);
    return parsed && typeof parsed === "object" ? parsed.experiment ?? null : undefined;
  } catch (_error) {
    return undefined;
  }
}

// Which experiment this unit is in. The leader publishes a retained message on
// every (re)assignment; the HTTP read covers the first load and older leaders.
function useAssignment(unit, broker) {
  const [experiment, setExperiment] = useState(undefined); // undefined: not known yet
  const [worker, setWorker] = useState(undefined); // {is_active, model_name, model_version} | null if not in inventory
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(
    () =>
      broker.subscribe([`pioreactor/${unit}/$experiment/assignment`], (_topic, payload) => {
        const next = payload === "" ? undefined : parseAssignment(payload);
        if (next !== undefined) setExperiment(next);
      }),
    [broker, unit],
  );

  // Re-read after the broker reconnects: the leader may have been down.
  useEffect(() => broker.onStatus((connected) => connected && refresh()), [broker, refresh]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;
    leaderApi(`/workers/${enc(unit)}`, { signal })
      .then(setWorker)
      .catch((error) => {
        if (error.status === 404) setWorker(null);
      });
    leaderApi(`/workers/${enc(unit)}/experiment`, { signal })
      .then((data) => setExperiment(data.experiment ?? null))
      .catch((error) => {
        if (error.status === 404) setExperiment(null);
      });
    return () => controller.abort();
  }, [unit, version]);

  return { experiment, worker, refresh };
}

function useExperimentMetadata(experiment) {
  const [metadata, setMetadata] = useState(null);
  useEffect(() => {
    setMetadata(null);
    if (!experiment) return undefined;
    const controller = new AbortController();
    leaderApi(`/experiments/${enc(experiment)}`, { signal: controller.signal })
      .then(setMetadata)
      .catch(() => {});
    return () => controller.abort();
  }, [experiment]);
  return metadata;
}

function Session({ unit, config, children }) {
  const broker = useMemo(() => createBroker(config.mqtt, `kiosk-${unit}`), [config, unit]);
  useEffect(() => () => broker.end(), [broker]);

  const leaderHostname = config["cluster.topology"]?.leader_hostname || null;
  const { experiment, worker, refresh } = useAssignment(unit, broker);
  const experimentMetadata = useExperimentMetadata(experiment);

  const value = useMemo(
    () => ({
      unit,
      config,
      broker,
      leaderHostname,
      isLeader: unit === leaderHostname,
      experiment, // undefined while unknown, null when unassigned
      experimentMetadata,
      worker,
      refreshAssignment: refresh,
    }),
    [unit, config, broker, leaderHostname, experiment, experimentMetadata, worker, refresh],
  );

  return <KioskContext.Provider value={value}>{children}</KioskContext.Provider>;
}

export function KioskProvider({ children }) {
  const info = useBootInfo();

  if (!info) {
    return <div className="boot">Connecting to this Pioreactor...</div>;
  }

  setLeaderOrigin(leaderOriginFor(info.unit, info.config));

  return (
    <Session unit={info.unit} config={info.config}>
      {children}
    </Session>
  );
}

// Environment for jobs started from this screen. The leader adds the same values
// when it starts jobs, so the job doesn't have to ask the leader for them.
export function jobEnv({ experiment, worker }) {
  const env = { EXPERIMENT: experiment, JOB_SOURCE: "user" };
  if (worker) {
    env.ACTIVE = String(Number(worker.is_active));
    if (worker.model_name && worker.model_version) {
      env.MODEL_NAME = worker.model_name;
      env.MODEL_VERSION = worker.model_version;
    }
  }
  return env;
}
