import { useEffect, useMemo, useState } from "react";
import { navigate, useDisplay } from "../context";
import Header from "../Header";
import { usePendingStates, useTopicValues } from "../hooks";
import { AsyncButton, Icon, ReadValue, StateBadge, Tabs, useConfirm, useToast } from "../ui";
import { EditField } from "../Keyboard";
import { firstOd, fmt, fmtFixed, readDisplay, readNumber } from "../values";
import { getAutomationDescriptors, getWorkerJobDescriptors, runPioreactorJob } from "../../utils/jobs";
import { experimentPathSegment } from "../../utils/url";
import AutomationSheet from "./AutomationSheet";
import DosingPanel from "./DosingPanel";
import LedPanel from "./LedPanel";
import ChartView from "./ChartView";

// Live readings that aren't in the job descriptors but are worth seeing at the bench.
const LIVE_EXTRAS = {
  stirring: [{ key: "measured_rpm", label: "Measured", unit: "RPM", format: (p) => fmtFixed(readNumber(p, "measured_rpm"), 0) }],
  od_reading: [{ key: "ods", label: "Latest OD", format: (p) => fmt(firstOd(p)) }],
  growth_rate_calculating: [
    { key: "growth_rate", label: "Growth rate", unit: "h⁻¹", format: (p) => fmtFixed(readNumber(p, "growth_rate"), 3) },
    { key: "od_filtered", label: "Normalized OD", format: (p) => fmtFixed(readNumber(p, "od_filtered"), 3) },
  ],
  temperature_automation: [{ key: "temperature", label: "Temperature", unit: "℃", format: (p) => fmtFixed(readNumber(p, "temperature"), 2) }],
};

const RUNNING = new Set(["init", "ready", "sleeping"]);

export function updateJobSettings(unit, experiment, job, settings) {
  return fetch(`/api/workers/${unit}/jobs/update/job_name/${job}/experiments/${experimentPathSegment(experiment)}`, {
    method: "PATCH",
    body: JSON.stringify({ settings }),
    headers: { Accept: "application/json", "Content-Type": "application/json" },
  }).then((response) => {
    if (!response.ok) throw new Error(`Error ${response.status}.`);
  });
}

function JobRow({ descriptor, state, pending, get, onStart, onSetState, onEdit }) {
  const job = descriptor.job_name;
  const running = RUNNING.has(state);
  const subtext = descriptor.subtext ? readDisplay(get(job, descriptor.subtext), descriptor.subtext) : null;
  const settings = descriptor.published_settings.filter((setting) => setting.display && setting.key !== descriptor.subtext);
  const extras = LIVE_EXTRAS[job] || [];
  const busy = Boolean(pending);

  return (
    <div className="job-row">
      <div className="job-name">
        <strong className="truncate">{descriptor.display_name}</strong>
        <StateBadge state={state} pending={pending?.label} />
        {running && subtext && <span className="sub truncate">{subtext.replace(/_/g, " ")}</span>}
      </div>
      <div className="job-settings">
        {running &&
          extras.map((extra) => (
            <ReadValue key={extra.key} label={extra.label} value={extra.format(get(job, extra.key))} unit={extra.unit} />
          ))}
        {running &&
          settings.map((setting) => {
            const raw = get(job, setting.key);
            const value = readDisplay(raw, setting.key);
            if (setting.editable === false) {
              return <ReadValue key={setting.key} label={setting.label} value={value} unit={setting.unit} />;
            }
            return (
              <EditField
                key={setting.key}
                label={setting.label}
                value={setting.type === "numeric" && value !== null ? fmt(value, 4) : value}
                unit={setting.unit}
                type={setting.type === "numeric" ? "number" : "text"}
                hint={setting.description}
                onCommit={(next) => onEdit(job, setting.key, next)}
              />
            );
          })}
      </div>
      <div className="job-actions">
        {!running && (
          <button className="btn primary" disabled={busy} onClick={() => onStart(descriptor)}>
            Start
          </button>
        )}
        {state === "ready" && (
          <button className="btn" disabled={busy} onClick={() => onSetState(job, "sleeping")}>
            Pause
          </button>
        )}
        {state === "sleeping" && (
          <button className="btn" disabled={busy} onClick={() => onSetState(job, "ready")}>
            Resume
          </button>
        )}
        {(running || state === "lost") && (
          <button className="btn danger" disabled={busy} onClick={() => onSetState(job, "disconnected")}>
            Stop
          </button>
        )}
      </div>
    </div>
  );
}

function Activities({ unit, experiment, get }) {
  const toast = useToast();
  const [descriptors, setDescriptors] = useState(null);
  const [error, setError] = useState(null);
  const [automationType, setAutomationType] = useState(null);

  useEffect(() => {
    let ignore = false;
    getWorkerJobDescriptors(unit)
      .then((list) => !ignore && setDescriptors(list.filter((job) => job.display)))
      .catch((err) => !ignore && setError(err.message));
    return () => {
      ignore = true;
    };
  }, [unit]);

  const states = useMemo(
    () => Object.fromEntries((descriptors || []).map((d) => [d.job_name, get(d.job_name, "$state")])),
    [descriptors, get],
  );
  const { pending, mark, clear } = usePendingStates(states, {
    onExpire: (job, entry) => {
      const name = descriptors?.find((d) => d.job_name === job)?.display_name || job;
      toast.error(`${name}: no response after "${entry.label.replace("...", "")}". Check Logs for details.`);
    },
  });

  // Warm the automation descriptor cache so the start sheet opens instantly.
  useEffect(() => {
    if (!descriptors) return;
    descriptors
      .filter((d) => d.job_name.endsWith("_automation"))
      .forEach((d) => getAutomationDescriptors(unit, d.job_name.replace(/_automation$/, "")).catch(() => {}));
  }, [descriptors, unit]);

  const onStart = (descriptor) => {
    const job = descriptor.job_name;
    if (job.endsWith("_automation")) {
      setAutomationType(job.replace(/_automation$/, ""));
      return;
    }
    mark(job, "Starting...", ["init", "ready"]);
    runPioreactorJob(unit, experiment, job).catch((err) => {
      clear(job);
      toast.error(err);
    });
  };

  const onSetState = (job, state) => {
    const label = { sleeping: "Pausing...", ready: "Resuming...", disconnected: "Stopping..." }[state];
    mark(job, label, state === "disconnected" ? ["disconnected", "lost"] : [state]);
    updateJobSettings(unit, experiment, job, { $state: state }).catch((err) => {
      clear(job);
      toast.error(err);
    });
  };

  const onEdit = (job, key, value) => updateJobSettings(unit, experiment, job, { [key]: value });

  if (error) return <div className="empty">Could not load activities: {error}</div>;
  if (!descriptors) return <div className="empty">Loading...</div>;

  return (
    <>
      <div className="list">
        {descriptors.map((descriptor) => (
          <JobRow
            key={descriptor.job_name}
            descriptor={descriptor}
            state={states[descriptor.job_name]}
            pending={pending[descriptor.job_name]}
            get={get}
            onStart={onStart}
            onSetState={onSetState}
            onEdit={onEdit}
          />
        ))}
      </div>
      {automationType && (
        <AutomationSheet
          unit={unit}
          experiment={experiment}
          automationType={automationType}
          onClose={() => setAutomationType(null)}
          onStarted={() => {
            mark(`${automationType}_automation`, "Starting...", ["init", "ready"]);
            setAutomationType(null);
          }}
        />
      )}
    </>
  );
}

const TABS = [
  { value: "activities", label: "Activities" },
  { value: "dosing", label: "Dosing" },
  { value: "leds", label: "LEDs" },
  { value: "chart", label: "Chart" },
];

export default function Unit({ unit }) {
  const { experiment, units, labelFor } = useDisplay();
  const confirm = useConfirm();
  const toast = useToast();
  const [tab, setTab] = useState("activities");
  const topics = useMemo(
    () => (experiment ? [`pioreactor/${unit}/${experiment}/+/+`, `pioreactor/${unit}/$experiment/monitor/$state`] : []),
    [unit, experiment],
  );
  const values = useTopicValues(topics, 600);
  const get = useMemo(() => (job, key) => values[`pioreactor/${unit}/${experiment}/${job}/${key}`], [values, unit, experiment]);
  const worker = units?.find((entry) => entry.pioreactor_unit === unit);
  const monitor = values[`pioreactor/${unit}/$experiment/monitor/$state`];
  const label = labelFor(unit);

  const identify = async () => {
    const response = await fetch(`/api/workers/${unit}/blink`, { method: "POST" });
    if (!response.ok) throw new Error("Could not reach this Pioreactor.");
    toast(`${label} is blinking its blue LED.`);
  };

  const stopAll = async () => {
    const ok = await confirm({
      title: `Stop all activities on ${label}?`,
      message: "This immediately stops every activity on this Pioreactor, and any experiment profiles running on it.",
      confirmText: "Stop all",
      danger: true,
    });
    if (!ok) return;
    const response = await fetch(`/api/workers/${unit}/jobs/stop/experiments/${experimentPathSegment(experiment)}`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Could not stop activities. Try again.");
    toast("Stopping all activities...");
  };

  return (
    <>
      <Header
        title={label}
        subtitle={label !== unit ? unit : null}
        onBack={() => navigate("overview")}
        backLabel="Back to Pioreactors"
        showExperiment={false}
        actions={
          <>
            {monitor === "lost" && <span className="badge lost">Lost</span>}
            <AsyncButton className="btn" onClick={identify}>
              <Icon name="identify" />
              Identify
            </AsyncButton>
            <AsyncButton className="btn danger" onClick={stopAll}>
              <Icon name="stop" />
              Stop all
            </AsyncButton>
          </>
        }
      />
      <div className={`content ${tab === "chart" ? "fill" : ""}`}>
        <Tabs tabs={TABS} value={tab} onChange={setTab} />
        {units && !worker && <div className="banner">{unit} is not assigned to {experiment}.</div>}
        {worker && worker.is_active !== 1 && <div className="banner">{label} is inactive. Activities can't be started.</div>}
        {tab === "activities" && <Activities unit={unit} experiment={experiment} get={get} />}
        {tab === "dosing" && <DosingPanel unit={unit} experiment={experiment} get={get} />}
        {tab === "leds" && <LedPanel unit={unit} experiment={experiment} get={get} />}
        {tab === "chart" && <ChartView unit={unit} />}
      </div>
    </>
  );
}
