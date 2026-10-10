import { useCallback, useMemo } from "react";
import { enc, unitApi } from "./api";
import { jobEnv, useKiosk } from "./context";
import { useTopicValues } from "./hooks";

// Descriptors only change when plugins change, so cache them for the session.
// Starting the request early means sheets open instantly later.
const cache = new Map();

function cached(key, load) {
  if (!cache.has(key)) {
    cache.set(
      key,
      load().catch((error) => {
        cache.delete(key);
        throw error;
      }),
    );
  }
  return cache.get(key);
}

export const getJobDescriptors = () => cached("jobs", () => unitApi("/jobs/descriptors"));

export const getAutomationDescriptors = (type) =>
  cached(`automations:${type}`, () => unitApi(`/automations/descriptors/${enc(type)}`));

// Every job's $state and published settings for this unit and experiment, from one
// wildcard subscription. get(job, key) returns the raw payload string.
export function useUnitValues(throttleMs = 600) {
  const { unit, experiment } = useKiosk();
  const prefix = experiment ? `pioreactor/${unit}/${experiment}` : null;
  const values = useTopicValues(prefix ? [`${prefix}/+/+`] : [], throttleMs);
  const get = useCallback((job, key) => values[`${prefix}/${job}/${key}`], [values, prefix]);
  return get;
}

// Unit-local job control. It keeps working while the leader is unreachable, as
// long as the experiment is known.
export function useJobControl() {
  const kiosk = useKiosk();
  const { unit, experiment, broker } = kiosk;
  const env = useMemo(() => jobEnv(kiosk), [kiosk]);

  return useMemo(
    () => ({
      run(job, { options = {}, args = [] } = {}) {
        if (!experiment) return Promise.reject(new Error("Join an experiment first."));
        return unitApi(`/jobs/run/job_name/${enc(job)}`, {
          method: "POST",
          body: { options, args, env, config_overrides: [] },
        });
      },
      stop(job) {
        return unitApi("/jobs/stop", { method: "POST", body: { job_name: job, ...(experiment ? { experiment } : {}) } });
      },
      stopAll() {
        if (!experiment) return unitApi("/jobs/stop/all", { method: "POST" });
        return unitApi("/jobs/stop", { method: "POST", body: { experiment } });
      },
      // What the leader's PATCH endpoint does, without the extra hop and the
      // per-request MQTT client on the leader.
      set(job, setting, value) {
        return broker.publish(`pioreactor/${unit}/${experiment}/${job}/${setting}/set`, String(value), { qos: 1 });
      },
    }),
    [unit, experiment, broker, env],
  );
}
