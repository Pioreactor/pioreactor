import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { unitApi } from "../api";
import { useKiosk } from "../context";
import { useAsync, useBrokerConnected, usePendingStates } from "../hooks";
import { Icon } from "../icons";
import { EditField } from "../Keyboard";
import { getAutomationDescriptors, getJobDescriptors, useJobControl, useUnitValues } from "../jobs";
import { AsyncButton, Empty, ReadValue, Segmented, Sheet, StateBadge, useConfirm, useToast } from "../ui";
import { navigate, usePage } from "../router";
import { fmt, readDisplay, RUNNING_STATES } from "../values";
import AutomationSheet from "./AutomationSheet";
import Dosing from "./Dosing";
import Leds, { AllLedsOff } from "./Leds";

// One-shot actions at the bench. Their descriptors have display: false.
const TOOLS = [
  { job: "self_test", label: "Self-test", action: "Run self-test" },
  { job: "od_blank", label: "OD blank", action: "Run OD blank" },
];

const PENDING_LABELS = { sleeping: "Pausing...", ready: "Resuming...", disconnected: "Stopping..." };

const shownSettings = (descriptor) =>
  descriptor.published_settings.filter((setting) => setting.display && setting.key !== descriptor.subtext);

// Props are primitives (plus stable callbacks) so memo() skips unchanged rows.
// A row shows what the job is doing; its settings open in a sheet, so the list
// stays short and doesn't re-render as settings change.
const JobRow = memo(function JobRow({ descriptor, state, pendingLabel, subtext, onStart, onSetState, onStop, onOpen }) {
  const job = descriptor.job_name;
  const running = RUNNING_STATES.has(state);
  const busy = Boolean(pendingLabel);
  const openable = running && shownSettings(descriptor).length > 0;
  const name = (
    <span className="job-name">
      <strong className="truncate">{descriptor.display_name}</strong>
      <StateBadge state={state} pending={pendingLabel} />
      {running && subtext && <span className="sub truncate">{subtext.replace(/_/g, " ")}</span>}
    </span>
  );

  return (
    <div className="job-row">
      {openable ? (
        <button type="button" className="job-main" onClick={() => onOpen(job)}>
          {name}
          <Icon name="forward" className="job-open" />
        </button>
      ) : (
        <div className="job-main">{name}</div>
      )}
      <div className="job-actions">
        {!running && state !== "lost" && (
          <button type="button" className="btn primary" disabled={busy} onClick={() => onStart(descriptor)}>
            Start
          </button>
        )}
        {state === "ready" && (
          <button type="button" className="btn" disabled={busy} onClick={() => onSetState(job, "sleeping")}>
            <Icon name="pause" />
            Pause
          </button>
        )}
        {state === "sleeping" && (
          <button type="button" className="btn" disabled={busy} onClick={() => onSetState(job, "ready")}>
            <Icon name="play" />
            Resume
          </button>
        )}
        {(running || state === "lost") && (
          <button type="button" className="btn danger" disabled={busy} onClick={() => onStop(job)}>
            <Icon name="stop" />
            Stop
          </button>
        )}
      </div>
    </div>
  );
});

// A running job's displayed settings, live; editable ones open the keyboard.
function JobSettingsSheet({ descriptor, get, onEdit, onClose }) {
  const job = descriptor.job_name;
  return (
    <Sheet title={descriptor.display_name} onClose={onClose}>
      {shownSettings(descriptor).map((setting) => {
        const value = readDisplay(get(job, setting.key), setting.key);
        if (setting.editable === false) {
          return <ReadValue key={setting.key} className="wide" label={setting.label} value={value} unit={setting.unit} />;
        }
        const numeric = setting.type === "numeric";
        return (
          <EditField
            key={setting.key}
            className="wide"
            label={setting.label}
            value={numeric && value !== null ? fmt(value, 4) : value}
            unit={setting.unit}
            type={numeric ? "number" : "text"}
            hint={setting.description}
            onCommit={(next) => onEdit(job, setting.key, next)}
          />
        );
      })}
    </Sheet>
  );
}

function JobList({ get }) {
  const toast = useToast();
  const control = useJobControl();
  const descriptors = useAsync(() => getJobDescriptors(), []);
  const [automationType, setAutomationType] = useState(null);
  const [openJob, setOpenJob] = useState(null);

  const shown = useMemo(() => (descriptors.data || []).filter((descriptor) => descriptor.display), [descriptors.data]);
  const states = useMemo(() => Object.fromEntries(shown.map((d) => [d.job_name, get(d.job_name, "$state")])), [shown, get]);
  const nameOf = useCallback((job) => shown.find((d) => d.job_name === job)?.display_name || job, [shown]);

  const { pending, mark, clear } = usePendingStates(states, {
    onExpire: (job, entry) => toast.error(`${nameOf(job)}: no response after "${entry.label.replace("...", "")}". Check Logs for details.`),
  });

  // Warm the automation descriptors so the start sheet opens instantly.
  useEffect(() => {
    shown
      .filter((d) => d.job_name.endsWith("_automation"))
      .forEach((d) => getAutomationDescriptors(d.job_name.replace(/_automation$/, "")).catch(() => {}));
  }, [shown]);

  const onStart = useCallback(
    (descriptor) => {
      const job = descriptor.job_name;
      if (job.endsWith("_automation")) {
        setAutomationType(job.replace(/_automation$/, ""));
        return;
      }
      mark(job, "Starting...", ["init", "ready"]);
      control.run(job).catch((error) => {
        clear(job);
        toast.error(error);
      });
    },
    [control, mark, clear, toast],
  );

  const onSetState = useCallback(
    (job, state) => {
      mark(job, PENDING_LABELS[state], [state]);
      control.set(job, "$state", state).catch((error) => {
        clear(job);
        toast.error(error);
      });
    },
    [control, mark, clear, toast],
  );

  const onStop = useCallback(
    (job) => {
      mark(job, PENDING_LABELS.disconnected, ["disconnected"]);
      control.stop(job).catch((error) => {
        clear(job);
        toast.error(error);
      });
    },
    [control, mark, clear, toast],
  );

  const onEdit = useCallback((job, key, value) => control.set(job, key, value), [control]);

  // The settings sheet closes when its job stops.
  const openDescriptor = openJob && RUNNING_STATES.has(states[openJob]) ? shown.find((d) => d.job_name === openJob) : null;
  useEffect(() => {
    if (openJob && !openDescriptor) setOpenJob(null);
  }, [openJob, openDescriptor]);

  if (descriptors.error) return <Empty>Could not load activities: {descriptors.error}</Empty>;
  if (!descriptors.data) return <Empty>Loading activities...</Empty>;

  return (
    <>
      <div className="list">
        {shown.map((descriptor) => {
          const job = descriptor.job_name;
          return (
            <JobRow
              key={job}
              descriptor={descriptor}
              state={states[job]}
              pendingLabel={pending[job]?.label}
              subtext={descriptor.subtext ? readDisplay(get(job, descriptor.subtext), descriptor.subtext) : null}
              onStart={onStart}
              onSetState={onSetState}
              onStop={onStop}
              onOpen={setOpenJob}
            />
          );
        })}
      </div>
      {openDescriptor && (
        <JobSettingsSheet descriptor={openDescriptor} get={get} onEdit={onEdit} onClose={() => setOpenJob(null)} />
      )}
      {automationType && (
        <AutomationSheet
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

function Tools({ get }) {
  const control = useJobControl();
  const toast = useToast();

  return (
    <>
      <h2 className="section-title">Tools</h2>
      <div className="btn-row">
        {TOOLS.map((tool) => {
          const running = RUNNING_STATES.has(get(tool.job, "$state"));
          return (
            <AsyncButton
              key={tool.job}
              className="btn"
              disabled={running}
              onClick={async () => {
                await control.run(tool.job);
                toast(`${tool.label} started. Results appear in Logs.`);
              }}
            >
              <Icon name="tools" />
              {running ? `${tool.label} running...` : tool.action}
            </AsyncButton>
          );
        })}
      </div>
    </>
  );
}

// Without the broker there are no live states, but this unit still knows what
// it's running and can stop it. (Once workers bridge a local broker, losing the
// leader no longer lands here: the screen keeps its broker and full control.)
function OfflineJobs() {
  const toast = useToast();
  const running = useAsync((signal) => unitApi("/jobs/running", { signal }), [], { refreshMs: 5000 });

  const stop = async (job) => {
    await unitApi("/jobs/stop", { method: "POST", body: { job_name: job } });
    toast(`Stopping ${job.replace(/_/g, " ")}...`);
    running.reload();
  };

  const rows = (running.data || []).filter((row) => !row.is_long_running_job);

  return (
    <>
      <div className="banner">
        Can't reach the message broker, so live readings are unavailable. Activities running on this Pioreactor are
        listed below.
      </div>
      {running.data && rows.length === 0 && <Empty>No activities are running.</Empty>}
      <div className="list">
        {rows.map((row) => (
          <div className="list-row" key={row.job_id}>
            <div className="grow">
              <div className="strong truncate">{row.job_name.replace(/_/g, " ")}</div>
              <div className="sub truncate">{row.experiment}</div>
            </div>
            <AsyncButton className="btn danger" onClick={() => stop(row.job_name)}>
              <Icon name="stop" />
              Stop
            </AsyncButton>
          </div>
        ))}
      </div>
    </>
  );
}

function StopAll() {
  const { unit } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const control = useJobControl();

  const stopAll = async () => {
    const ok = await confirm({
      title: `Stop all activities on ${unit}?`,
      message: "This immediately stops every activity on this Pioreactor.",
      confirmText: "Stop all",
      danger: true,
    });
    if (!ok) return;
    await control.stopAll();
    toast("Stopping all activities...");
  };

  return (
    <AsyncButton className="btn danger" onClick={stopAll}>
      <Icon name="stop" />
      Stop all
    </AsyncButton>
  );
}

const TABS = [
  { value: "", label: "Activities" },
  { value: "dosing", label: "Dosing" },
  { value: "leds", label: "LEDs" },
];

export default function Activities() {
  const { experiment, role } = useKiosk();
  const connected = useBrokerConnected();
  const page = usePage();
  const tab = TABS.some((t) => t.value === page) ? page : "";
  const get = useUnitValues();

  if (!connected) {
    return (
      <div className="content">
        <OfflineJobs />
      </div>
    );
  }
  if (role === "unjoined") return <Empty>Activities start once this Pioreactor is in a cluster and an experiment.</Empty>;
  if (experiment === undefined) return <Empty>Waiting for the leader...</Empty>;
  if (experiment === null) {
    return (
      <Empty>
        <Icon name="experiment" className="empty-icon" />
        <h1>Not in an experiment</h1>
        {role === "worker"
          ? "Tap the experiment button above to join one."
          : "Tap the experiment button above to start a new one or join one."}
      </Empty>
    );
  }

  return (
    <div className="content">
      <div className="toolbar">
        <Segmented label="Activities section" options={TABS} value={tab} onChange={navigate} />
        <span className="grow" />
        {tab === "leds" && <AllLedsOff />}
        <StopAll />
      </div>
      {tab === "" && (
        <>
          <JobList get={get} />
          <Tools get={get} />
        </>
      )}
      {tab === "dosing" && <Dosing get={get} />}
      {tab === "leds" && <Leds get={get} />}
    </div>
  );
}
