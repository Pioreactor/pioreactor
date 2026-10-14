// Experiments and membership, on the leader's /api. Experiments belong to the
// leader (CLUSTER_MODEL.md: "experiments are print jobs"), so every screen goes
// through it; only leaders' screens create and end them.
import { enc, leaderApi, unitApi, waitForTask } from "./api";

export const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

export function formatDate(timestamp) {
  const ms = Date.parse(timestamp);
  return Number.isFinite(ms) ? new Date(ms).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : null;
}

// The leader's own rules (api.py _validate_experiment_name), checked before sending.
export function validateExperimentName(raw) {
  const name = raw.trim();
  if (!name) return "Enter a name.";
  if (name.length >= 200) return "Use fewer than 200 characters.";
  if (name.toLowerCase() === "current") return "\"current\" is reserved. Choose another name.";
  if (name.startsWith("_testing")) return "Names can't start with \"_testing\".";
  if (/[#$%+/?\\]/.test(name)) return "Names can't contain # $ % + / ? or \\.";
  return null;
}

// The leader's rule for worker names (pioreactor_unit_name_can_be_persisted).
export function validateUnitName(raw) {
  const name = raw.trim();
  if (!name) return "Enter a name.";
  if (!/^[A-Za-z0-9-]+$/.test(name)) return "Use the hostname only: letters, digits and dashes, without .local.";
  return null;
}

export const listExperiments = (signal) => leaderApi("/experiments", { signal });

export const createExperiment = (name) => leaderApi("/experiments", { method: "POST", body: { experiment: name } });

// Reassigns the unit if it's in another experiment; that stops its jobs there.
export const assignUnit = (experiment, unit) =>
  leaderApi(`/experiments/${enc(experiment)}/workers`, { method: "PUT", body: { pioreactor_unit: unit } });

export const unassignUnit = (experiment, unit) =>
  leaderApi(`/experiments/${enc(experiment)}/workers/${enc(unit)}`, { method: "DELETE" });

// Stops every unit's activities in it and unassigns them all. Its data is kept.
export const endExperiment = (experiment) => leaderApi(`/experiments/${enc(experiment)}/workers`, { method: "DELETE" });

export const listUnitsIn = (experiment, signal) => leaderApi(`/experiments/${enc(experiment)}/workers`, { signal });

/* ---------- Leaders' screens only: membership ---------- */

export const listWorkers = (signal) => leaderApi("/workers", { signal });

export const listAssignments = (signal) => leaderApi("/workers/assignments", { signal });

// Standalone units nearby (mDNS) that this cluster doesn't have yet. Takes a few seconds.
export const discoverUnits = (signal) => leaderApi("/workers/discover", { signal });

// Adds a unit as a worker. The unit keeps its own model and reports it, so no
// model is sent. Takes minutes: SSH keys, then the unit configures itself and reboots.
export async function addUnit(name) {
  const task = await leaderApi("/workers/setup", { method: "POST", body: { name } });
  return waitForTask(task.result_url_path, { delayMs: 1000, timeoutMs: 600000 });
}

// The leader stops the unit's activities, and the unit leaves and reboots.
export const removeUnit = (unit) => leaderApi(`/workers/${enc(unit)}`, { method: "DELETE" });

export const setUnitActive = (unit, active) =>
  leaderApi(`/workers/${enc(unit)}/is_active`, { method: "PUT", body: { is_active: active ? 1 : 0 } });

/* ---------- Leaders' screens only: experiment profiles ---------- */

// Profiles run on the leader, so its own /unit_api starts and stops them.
export const listProfiles = (signal) => leaderApi("/experiment_profiles", { signal });

export const listRunningProfiles = (experiment, signal) =>
  leaderApi(`/experiments/${enc(experiment)}/experiment_profiles/running`, { signal });

export async function runProfile(file, experiment) {
  const task = await unitApi("/jobs/run/job_name/experiment_profile", {
    method: "POST",
    body: { args: ["execute", file, experiment], options: {}, env: { JOB_SOURCE: "user" } },
  });
  const result = await waitForTask(task.result_url_path);
  if (result?.ok !== true) throw new Error(result?.error || "The profile didn't start.");
  return result;
}

export const stopProfile = (jobId) => unitApi("/jobs/stop", { method: "POST", body: { job_id: jobId } });

/* ---------- Workers' screens: leaving ---------- */

// Like `pio cluster leave`: refuse while activities run, tell the leader (which
// asks this unit to leave), and leave directly only if the leader can't.
export async function activitiesRunningHere(signal) {
  const running = await unitApi("/jobs/running", { signal });
  return (running || []).filter((row) => !row.is_long_running_job).map((row) => row.job_name);
}

export async function leaveCluster(unit, { leaderReachable }) {
  if (leaderReachable) {
    try {
      await removeUnit(unit);
      return;
    } catch (error) {
      if (error.status !== 404) throw error;
      // The leader doesn't list this unit anymore; leave on our own.
    }
  }
  await unitApi("/cluster/leave", { method: "POST" });
}
