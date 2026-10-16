import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { enc, leaderApi, setLeaderOrigin, unitApi } from "./api";
import { useAsync } from "./hooks";
import { createBroker } from "./mqtt";
import { useToast } from "./ui";
import { driveName, useUsbStatus } from "./usb";

export const KioskContext = createContext(null);
export const useKiosk = () => useContext(KioskContext);

const BOOT_RETRY_MS = 3000;
// How often a screen checks that its leader answers. Cheap: one row from the leader.
const LEADER_PROBE_MS = 30000;
const LEADER_PROBE_TIMEOUT_MS = 6000;

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

// What this screen is, from the cluster model (CLUSTER_MODEL.md):
// - "standalone": a leader with no other Pioreactors (a cluster of one);
// - "leader": a leader with workers; its screen also runs the cluster;
// - "worker": in someone else's cluster; its screen controls only this unit;
// - "unjoined": no leader configured (it left a cluster), waiting to be added.
export function roleOf({ leaderHostname, isLeader, otherUnits }) {
  if (!leaderHostname) return "unjoined";
  if (!isLeader) return "worker";
  return otherUnits > 0 ? "leader" : "standalone";
}

export function parseAssignment(payload) {
  try {
    const parsed = JSON.parse(payload);
    return parsed && typeof parsed === "object" ? parsed.experiment ?? null : undefined;
  } catch (_error) {
    return undefined;
  }
}

function withTimeout(signal, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  const onAbort = () => controller.abort();
  signal.addEventListener("abort", onAbort, { once: true });
  return {
    signal: controller.signal,
    done: () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
    },
  };
}

// Whether the leader answers, and what it knows about this unit. The broker
// connection doesn't tell us: once workers bridge a local broker, the screen stays
// connected while the leader is away. So the screen asks the leader directly, on
// boot, every 30 s, and whenever the broker connection changes.
//
// On the leader, the same request lists every worker, which also tells a
// standalone unit from the leader of a cluster.
function useLeaderLink(unit, broker, leaderHostname, isLeader) {
  const [link, setLink] = useState({ reachable: undefined, worker: undefined, workers: undefined });
  const [version, setVersion] = useState(0);
  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => broker.onStatus(refresh), [broker, refresh]);

  useEffect(() => {
    if (!leaderHostname) {
      setLink({ reachable: false, worker: null, workers: undefined });
      return undefined;
    }
    const controller = new AbortController();
    let timer;

    const probe = async () => {
      const attempt = withTimeout(controller.signal, LEADER_PROBE_TIMEOUT_MS);
      try {
        if (isLeader) {
          const workers = await leaderApi("/workers", { signal: attempt.signal });
          const worker = workers.find((row) => row.pioreactor_unit === unit) || null;
          setLink({ reachable: true, worker, workers });
        } else {
          const worker = await leaderApi(`/workers/${enc(unit)}`, { signal: attempt.signal });
          setLink((previous) => ({ ...previous, reachable: true, worker }));
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error.status === 404) setLink((previous) => ({ ...previous, reachable: true, worker: null }));
        else if (!isLeader) setLink((previous) => ({ ...previous, reachable: false }));
      } finally {
        attempt.done();
      }
      if (!controller.signal.aborted) timer = setTimeout(probe, LEADER_PROBE_MS);
    };

    probe();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [unit, leaderHostname, isLeader, version]);

  return { ...link, refresh };
}

// Which experiment this unit is in. The leader publishes a retained message on
// every (re)assignment; the HTTP read covers the first load, and runs again
// whenever the leader comes back.
function useAssignment(unit, broker, leaderHostname, leaderReachable) {
  const [experiment, setExperiment] = useState(undefined); // undefined: not known yet
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

  useEffect(() => {
    if (!leaderHostname) {
      setExperiment(null);
      return undefined;
    }
    if (!leaderReachable) return undefined;
    const controller = new AbortController();
    leaderApi(`/workers/${enc(unit)}/experiment`, { signal: controller.signal })
      .then((data) => setExperiment(data.experiment ?? null))
      .catch((error) => {
        if (error.status === 404) setExperiment(null);
      });
    return () => controller.abort();
  }, [unit, leaderHostname, leaderReachable, version]);

  return { experiment, refresh };
}

// Whether this unit is in service. The unit owns it (the leader only mirrors it), so
// it's read locally and stays right while the leader is away. Re-read on the leader
// check's interval, since the web UI can change it too.
function useLocalActive() {
  const { data, reload } = useAsync((signal) => unitApi("/active", { signal }), [], { refreshMs: LEADER_PROBE_MS });
  return { active: data ? Boolean(data.is_active) : undefined, refresh: reload };
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
  const isLeader = Boolean(leaderHostname) && unit === leaderHostname;
  const link = useLeaderLink(unit, broker, leaderHostname, isLeader);
  const { experiment, refresh: refreshExperiment } = useAssignment(unit, broker, leaderHostname, link.reachable);
  const experimentMetadata = useExperimentMetadata(experiment);
  const { active, refresh: refreshActive } = useLocalActive();
  const otherUnits = (link.workers || []).filter((row) => row.pioreactor_unit !== unit).length;
  const role = roleOf({ leaderHostname, isLeader, otherUnits });
  const toast = useToast();
  const usb = useUsbStatus((next) => toast(`${driveName(next)} connected. Open USB to export data or install plugins.`));

  const refreshLink = link.refresh;
  const refreshAssignment = useCallback(() => {
    refreshExperiment();
    refreshLink();
  }, [refreshExperiment, refreshLink]);

  const value = useMemo(
    () => ({
      unit,
      config,
      broker,
      role,
      leaderHostname,
      isLeader,
      leaderReachable: link.reachable, // undefined until the first answer
      experiment, // undefined while unknown, null when unassigned
      experimentMetadata,
      worker: link.worker, // this unit's row on the leader; null if the leader doesn't list it
      active, // whether this unit is in service; undefined until the first read
      refreshActive,
      refreshAssignment,
      refreshCluster: refreshLink,
      usb, // this unit's USB status (/unit_api/usb), null until the first check
    }),
    [
      unit,
      config,
      broker,
      role,
      leaderHostname,
      isLeader,
      link.reachable,
      link.worker,
      active,
      refreshActive,
      experiment,
      experimentMetadata,
      refreshAssignment,
      refreshLink,
      usb,
    ],
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

// Environment for jobs started from this screen, as the leader adds when it starts
// jobs. The unit owns its model and whether it's active, so neither is passed.
export function jobEnv({ experiment }) {
  return { EXPERIMENT: experiment, JOB_SOURCE: "user" };
}
