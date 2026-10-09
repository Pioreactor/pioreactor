import { useMemo, useState } from "react";
import { navigate, useDisplay } from "../context";
import Header, { formatElapsed } from "../Header";
import { useJSON, useNow } from "../hooks";
import { AsyncButton, Icon, Sheet, Tabs, useConfirm, useToast } from "../ui";
import { EditField, useKeyboard } from "../Keyboard";
import { useExperiment } from "../../providers/ExperimentContext";
import { useRunningProfiles } from "../../providers/RunningProfilesContext";
import { experimentPathSegment } from "../../utils/url";

const INVALID_EXPERIMENT_NAME_CHARACTERS = /[#$%+/?\\]/;

const TABS = [
  { value: "current", label: "Current" },
  { value: "assign", label: "Assign Pioreactors" },
  { value: "profiles", label: "Profiles" },
];

const jsonHeaders = { Accept: "application/json", "Content-Type": "application/json" };

async function ensureOk(response, message) {
  if (response.ok) return response;
  let detail = message;
  try {
    const payload = await response.json();
    detail = payload?.error || payload?.cause || message;
  } catch (_error) {
    // keep the generic message
  }
  throw new Error(detail);
}

function formatDate(iso) {
  const ms = Date.parse(iso);
  if (!Number.isFinite(ms)) return "";
  return new Date(ms).toLocaleString([], { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function SwitchSheet({ onClose }) {
  const { allExperiments, experimentMetadata, selectExperiment } = useExperiment();
  const toast = useToast();
  const sorted = useMemo(
    () => [...allExperiments].sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0)),
    [allExperiments],
  );
  return (
    <Sheet title="Switch experiment" onClose={onClose}>
      <div className="list">
        {sorted.map((exp) => (
          <button
            key={exp.experiment}
            className={`list-row ${exp.experiment === experimentMetadata.experiment ? "selected" : ""}`}
            onClick={() => {
              selectExperiment(exp.experiment);
              toast(`Now viewing ${exp.experiment}`);
              onClose();
            }}
          >
            <div className="grow">
              <div className="truncate">{exp.experiment}</div>
              <div className="sub">
                {formatDate(exp.created_at)} · {exp.worker_count ?? 0} assigned
              </div>
            </div>
            {exp.experiment === experimentMetadata.experiment && <Icon name="check" />}
          </button>
        ))}
      </div>
    </Sheet>
  );
}

function Current() {
  const { experiment, experimentMetadata, units, reloadUnits } = useDisplay();
  const { allExperiments, updateExperiment } = useExperiment();
  const openKeyboard = useKeyboard();
  const confirm = useConfirm();
  const toast = useToast();
  const now = useNow(60000);
  const [switching, setSwitching] = useState(false);

  const createExperiment = () => {
    const names = new Set(allExperiments.map((exp) => exp.experiment));
    openKeyboard({
      label: "New experiment name",
      type: "text",
      submitLabel: "Create",
      validate: (value) => {
        const trimmed = value.trim();
        if (!trimmed) return "Can't be blank.";
        if (INVALID_EXPERIMENT_NAME_CHARACTERS.test(trimmed)) return "Can't use $, %, #, \\, /, + or ? in an experiment name.";
        if (names.has(trimmed)) return "Experiment name already used. Choose another.";
        return null;
      },
      onSubmit: async (value) => {
        const name = value.trim();
        try {
          const response = await fetch("/api/experiments", {
            method: "POST",
            headers: jsonHeaders,
            body: JSON.stringify({
              experiment: name,
              created_at: new Date().toISOString(),
              description: "",
              tags: [],
              delta_hours: 0,
              worker_count: 0,
            }),
          });
          await ensureOk(response, "Could not create the experiment.");
          updateExperiment(await response.json(), true);
          toast(`Created ${name}. Now assign Pioreactors.`);
          navigate("experiment", "assign");
        } catch (error) {
          toast.error(error);
        }
      },
    });
  };

  const saveDescription = async (description) => {
    const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ description }),
    });
    await ensureOk(response, "Could not save the description.");
    updateExperiment(await response.json());
  };

  const end = async () => {
    const ok = await confirm({
      title: "End experiment?",
      message: "This stops any running activities in assigned Pioreactors, and unassigns all Pioreactors from this experiment.",
      confirmText: "End experiment",
      danger: true,
    });
    if (!ok) return;
    const response = await fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers`, { method: "DELETE" });
    await ensureOk(response, "Could not end the experiment.");
    reloadUnits();
    toast("Experiment ended. All Pioreactors were unassigned.");
  };

  return (
    <>
      {experiment ? (
        <div className="card" style={{ padding: "0.75rem", display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <div>
            <h2 style={{ fontSize: "1.3rem" }}>{experiment}</h2>
            <div className="muted" style={{ fontSize: "0.85rem" }}>
              Started {formatDate(experimentMetadata.created_at)} · running {formatElapsed(experimentMetadata.created_at, now)} ·{" "}
              {units?.length ?? 0} Pioreactors assigned
            </div>
          </div>
          <EditField
            className="wide"
            type="text"
            label="Description"
            value={experimentMetadata.description || ""}
            placeholder="Add a description"
            onCommit={saveDescription}
          />
        </div>
      ) : (
        <div className="empty">No experiment yet.</div>
      )}
      <div className="btn-row" style={{ marginTop: "0.75rem" }}>
        <button className="btn" onClick={() => setSwitching(true)}>
          Switch experiment
        </button>
        <button className="btn primary" onClick={createExperiment}>
          <Icon name="add" />
          Create new experiment
        </button>
        {experiment && (
          <AsyncButton className="btn danger" onClick={end} style={{ marginLeft: "auto" }}>
            End experiment
          </AsyncButton>
        )}
      </div>
      {switching && <SwitchSheet onClose={() => setSwitching(false)} />}
    </>
  );
}

function Assign() {
  const { experiment, reloadUnits, labelFor } = useDisplay();
  const confirm = useConfirm();
  const toast = useToast();
  const workers = useJSON("/api/workers");
  const assignments = useJSON("/api/workers/assignments");
  const [busy, setBusy] = useState(null);

  const assignedTo = useMemo(
    () => Object.fromEntries((assignments.data || []).map((row) => [row.pioreactor_unit, row.experiment])),
    [assignments.data],
  );
  const sorted = useMemo(
    () => [...(workers.data || [])].sort((a, b) => a.pioreactor_unit.localeCompare(b.pioreactor_unit, undefined, { numeric: true })),
    [workers.data],
  );

  const toggle = async (worker) => {
    const unit = worker.pioreactor_unit;
    const current = assignedTo[unit];
    if (current === experiment) {
      const ok = await confirm({
        title: `Unassign ${labelFor(unit)}?`,
        message: "Activities running on it for this experiment will stop.",
        confirmText: "Unassign",
        danger: true,
      });
      if (!ok) return;
    } else if (current) {
      const ok = await confirm({
        title: `Move ${unit} to this experiment?`,
        message: `It is assigned to ${current}. Its activities there will stop.`,
        confirmText: "Move here",
      });
      if (!ok) return;
    }
    setBusy(unit);
    try {
      const response =
        current === experiment
          ? await fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers/${unit}`, { method: "DELETE" })
          : await fetch(`/api/experiments/${experimentPathSegment(experiment)}/workers`, {
              method: "PUT",
              headers: jsonHeaders,
              body: JSON.stringify({ pioreactor_unit: unit }),
            });
      await ensureOk(response, "Could not update the assignment.");
      assignments.reload();
      reloadUnits();
    } catch (error) {
      toast.error(error);
    } finally {
      setBusy(null);
    }
  };

  if (!experiment) return <div className="empty">Create an experiment first.</div>;
  if (workers.error) return <div className="empty">Could not load Pioreactors.</div>;
  if (!workers.data) return <div className="empty">Loading...</div>;
  if (!sorted.length) return <div className="empty">No Pioreactors in the inventory yet. Add them from the web UI.</div>;

  return (
    <div className="list">
      {sorted.map((worker) => {
        const unit = worker.pioreactor_unit;
        const current = assignedTo[unit];
        const here = current === experiment;
        const inactive = worker.is_active !== 1;
        return (
          <button key={unit} className={`list-row ${here ? "selected" : ""}`} disabled={busy === unit || inactive} onClick={() => toggle(worker)}>
            <span className="dot" style={{ background: here ? "var(--primary)" : undefined }} />
            <div className="grow">
              <div className="truncate">{labelFor(unit) !== unit ? `${labelFor(unit)} (${unit})` : unit}</div>
              <div className="sub truncate">
                {inactive ? "Inactive" : here ? "Assigned to this experiment" : current ? `Assigned to ${current}` : "Unassigned"}
              </div>
            </div>
            {!inactive && (
              <span className={`btn small ${here ? "" : "primary"}`}>{busy === unit ? "Saving..." : here ? "Unassign" : current ? "Move here" : "Assign"}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function Profiles() {
  const { experiment } = useDisplay();
  const { runningProfiles, startProfile, stopProfile, loading } = useRunningProfiles();
  const confirm = useConfirm();
  const toast = useToast();
  const profiles = useJSON("/api/experiment_profiles");

  const sorted = useMemo(
    () =>
      [...(profiles.data || [])].sort((a, b) =>
        (a.experimentProfile?.experiment_profile_name || a.file).localeCompare(b.experimentProfile?.experiment_profile_name || b.file),
      ),
    [profiles.data],
  );

  const run = async (profile) => {
    const name = profile.experimentProfile?.experiment_profile_name || profile.file;
    const ok = await confirm({ title: `Run ${name}?`, message: `The profile will run in ${experiment}.`, confirmText: "Run profile" });
    if (!ok) return;
    await startProfile(profile.file, experiment);
    toast(`Started ${name}`);
  };

  const stop = async (job) => {
    const name = job.settings?.experiment_profile_name || "profile";
    const ok = await confirm({ title: `Stop ${name}?`, message: "Activities it started keep running.", confirmText: "Stop profile", danger: true });
    if (!ok) return;
    await stopProfile(job.job_id);
    toast(`Stopping ${name}...`);
  };

  return (
    <>
      <div className="section-title">Running</div>
      {runningProfiles.length === 0 ? (
        <div className="muted" style={{ fontSize: "0.9rem" }}>{loading ? "Loading..." : "No profiles running."}</div>
      ) : (
        <div className="list">
          {runningProfiles.map((job) => (
            <div className="list-row" key={job.job_id}>
              <div className="grow truncate">{job.settings?.experiment_profile_name || job.job_name}</div>
              <AsyncButton className="btn danger small" onClick={() => stop(job)}>
                <Icon name="stop" />
                Stop
              </AsyncButton>
            </div>
          ))}
        </div>
      )}
      <div className="section-title">Run a profile</div>
      {!profiles.data && <div className="muted">Loading...</div>}
      {profiles.data && sorted.length === 0 && <div className="muted">No experiment profiles. Create them in the web UI.</div>}
      <div className="list">
        {sorted.map((profile) => (
          <AsyncButton key={profile.file} className="list-row" onClick={() => run(profile)} disabled={!experiment}>
            <div className="grow">
              <div className="truncate">{profile.experimentProfile?.experiment_profile_name || profile.file}</div>
              {profile.experimentProfile?.metadata?.description && (
                <div className="sub truncate">{profile.experimentProfile.metadata.description}</div>
              )}
            </div>
            <Icon name="play" />
          </AsyncButton>
        ))}
      </div>
    </>
  );
}

export default function Experiment({ tab: initialTab }) {
  const [tab, setTab] = useState(initialTab === "assign" || initialTab === "profiles" ? initialTab : "current");
  return (
    <>
      <Header title="Experiment" showExperiment={false} />
      <div className="content">
        <Tabs tabs={TABS} value={tab} onChange={setTab} />
        {tab === "current" && <Current />}
        {tab === "assign" && <Assign />}
        {tab === "profiles" && <Profiles />}
      </div>
    </>
  );
}
