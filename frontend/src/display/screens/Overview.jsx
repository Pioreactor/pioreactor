import { memo, useMemo } from "react";
import { navigate, useDisplay } from "../context";
import Header from "../Header";
import { useTopicValues } from "../hooks";
import { AsyncButton, Icon, useConfirm, useToast } from "../ui";
import { ACTIVE_STATES, firstOd, fmt, fmtFixed, readNumber, shortJobName } from "../values";
import { experimentPathSegment } from "../../utils/url";

const PILL_ORDER = ["stirring", "od_reading", "growth_rate_calculating", "temperature_automation", "dosing_automation", "led_automation"];

function overviewTopics(experiment) {
  if (!experiment) return [];
  const base = `pioreactor/+/${experiment}`;
  return [
    `${base}/+/$state`,
    "pioreactor/+/$experiment/monitor/$state",
    `${base}/od_reading/ods`,
    `${base}/od_reading/od_fused`,
    `${base}/growth_rate_calculating/growth_rate`,
    `${base}/growth_rate_calculating/od_filtered`,
    `${base}/temperature_automation/temperature`,
    `${base}/stirring/measured_rpm`,
    `${base}/stirring/target_rpm`,
    `${base}/bioreactor/current_volume_ml`,
  ];
}

// Pull one unit's slice out of the shared topic map, so unchanged tiles skip rendering.
function unitSnapshot(values, unit, experiment) {
  const prefix = `pioreactor/${unit}/${experiment}/`;
  const get = (suffix) => values[prefix + suffix];
  const jobs = [];
  for (const topic of Object.keys(values)) {
    if (topic.startsWith(prefix) && topic.endsWith("/$state")) {
      const job = topic.slice(prefix.length, -"/$state".length);
      const state = values[topic];
      if (!job.includes("/") && ACTIVE_STATES.has(state)) jobs.push([job, state]);
    }
  }
  jobs.sort(([a], [b]) => {
    const ia = PILL_ORDER.indexOf(a);
    const ib = PILL_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.localeCompare(b);
  });
  const fused = readNumber(get("od_reading/od_fused"), "od_fused");
  return {
    monitor: values[`pioreactor/${unit}/$experiment/monitor/$state`],
    od: fused ?? firstOd(get("od_reading/ods")),
    odFiltered: readNumber(get("growth_rate_calculating/od_filtered"), "od_filtered"),
    growthRate: readNumber(get("growth_rate_calculating/growth_rate"), "growth_rate"),
    temperature: readNumber(get("temperature_automation/temperature"), "temperature"),
    rpm: readNumber(get("stirring/measured_rpm"), "measured_rpm") ?? readNumber(get("stirring/target_rpm")),
    volume: readNumber(get("bioreactor/current_volume_ml")),
    jobs: jobs.map(([job, state]) => `${job}:${state}`).join(","),
  };
}

function Metric({ label, value, unit }) {
  return (
    <div>
      <div className="metric-label">{label}</div>
      <div className="metric-value">
        {value ?? <span className="placeholder">—</span>}
        {value !== null && value !== undefined && unit && <small>{unit}</small>}
      </div>
    </div>
  );
}

// Props are primitives only, so memo() skips tiles whose readings didn't change.
const Tile = memo(function Tile({ unit, label, color, isActive, ...snapshot }) {
  const lost = snapshot.monitor === "lost";
  const jobs = snapshot.jobs ? snapshot.jobs.split(",").map((entry) => entry.split(":")) : [];
  return (
    <button
      className={`tile ${isActive ? "" : "inactive"} ${lost ? "lost" : ""}`}
      style={{ "--unit-color": color }}
      onClick={() => navigate("unit", unit)}
    >
      <div className="tile-head">
        <span className="tile-name truncate">
          {label}
          {label !== unit && <span className="muted">{unit}</span>}
        </span>
        {!isActive && <span className="badge">Inactive</span>}
        {lost && <span className="badge lost">Lost</span>}
      </div>
      <div className="metrics">
        <Metric label="OD" value={fmt(snapshot.od)} />
        <Metric label="Growth rate" value={fmtFixed(snapshot.growthRate, 3)} unit="h⁻¹" />
        <Metric label="Temperature" value={fmtFixed(snapshot.temperature, 1)} unit="℃" />
        <Metric label="Stirring" value={fmtFixed(snapshot.rpm, 0)} unit="RPM" />
      </div>
      <div className="job-pills">
        {jobs.length === 0 && <span className="job-pill">Idle</span>}
        {jobs.map(([job, state]) => (
          <span key={job} className={`job-pill ${state}`}>
            {shortJobName(job)}
            {state === "sleeping" ? " (paused)" : ""}
          </span>
        ))}
        {snapshot.volume !== null && <span className="job-pill">{fmt(snapshot.volume)} mL</span>}
      </div>
    </button>
  );
});

export default function Overview() {
  const { experiment, units, labelFor, unitColor } = useDisplay();
  const confirm = useConfirm();
  const toast = useToast();
  const topics = useMemo(() => overviewTopics(experiment), [experiment]);
  const values = useTopicValues(topics, 1000);
  const sorted = useMemo(
    () => [...(units || [])].sort((a, b) => a.pioreactor_unit.localeCompare(b.pioreactor_unit, undefined, { numeric: true })),
    [units],
  );

  const stopAll = async () => {
    const ok = await confirm({
      title: "Stop all activities?",
      message: "This immediately stops every activity on all assigned Pioreactors, and any experiment profiles running for this experiment.",
      confirmText: "Stop all",
      danger: true,
    });
    if (!ok) return;
    const response = await fetch(`/api/workers/$broadcast/jobs/stop/experiments/${experimentPathSegment(experiment)}`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Could not stop activities. Try again.");
    toast("Stopping all activities...");
  };

  const actions = sorted.length > 0 && (
    <AsyncButton className="btn danger" onClick={stopAll}>
      <Icon name="stop" />
      Stop all
    </AsyncButton>
  );

  return (
    <>
      <Header title="Pioreactors" subtitle={units ? `${units.length} assigned` : ""} actions={actions} />
      <div className="content">
        {!experiment && <div className="empty">No experiment yet. Create one from the Experiment screen.</div>}
        {experiment && units === null && <div className="empty">Loading...</div>}
        {experiment && units?.length === 0 && (
          <div className="empty">
            No Pioreactors are assigned to this experiment.
            <br />
            <button className="btn primary" onClick={() => navigate("experiment", "assign")}>
              <Icon name="add" />
              Assign Pioreactors
            </button>
          </div>
        )}
        <div className="tiles">
          {sorted.map((worker) => (
            <Tile
              key={worker.pioreactor_unit}
              unit={worker.pioreactor_unit}
              isActive={worker.is_active === 1}
              label={labelFor(worker.pioreactor_unit)}
              color={unitColor(worker.pioreactor_unit)}
              {...unitSnapshot(values, worker.pioreactor_unit, experiment)}
            />
          ))}
        </div>
      </div>
    </>
  );
}
