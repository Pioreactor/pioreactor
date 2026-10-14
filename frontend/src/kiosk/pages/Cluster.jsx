import { memo, useCallback, useMemo, useState } from "react";
import {
  addUnit,
  assignUnit,
  discoverUnits,
  endExperiment,
  formatDate,
  listAssignments,
  listExperiments,
  listProfiles,
  listRunningProfiles,
  listWorkers,
  plural,
  removeUnit,
  runProfile,
  setUnitActive,
  stopProfile,
  unassignUnit,
  validateUnitName,
} from "../cluster";
import { useKiosk } from "../context";
import { ExperimentList, useCreateExperiment } from "../ExperimentSheet";
import { useAsync, useTopicValues } from "../hooks";
import { Icon } from "../icons";
import { getJobDescriptors } from "../jobs";
import { useKeyboard } from "../Keyboard";
import { navigate, usePage } from "../router";
import { AsyncButton, Empty, ExperimentName, ReadValue, Segmented, Sheet, useConfirm, useToast } from "../ui";
import { RUNNING_STATES } from "../values";

// The leader's screen runs the cluster (CLUSTER_MODEL.md): add and remove
// Pioreactors, assign them to experiments, run profiles, and a status tile per
// unit. It doesn't control other units' jobs: that stays on their own screens
// and the global UI. A standalone unit sees the same page as a cluster of one.

const TABS = [
  {
    value: "cluster",
    label: (
      <>
        <Icon name="cluster" />
        Pioreactors
      </>
    ),
  },
  {
    value: "experiments",
    label: (
      <>
        <Icon name="experiment" />
        Experiments
      </>
    ),
  },
];

const parseJson = (payload) => {
  try {
    return JSON.parse(payload);
  } catch (_error) {
    return null;
  }
};

const humanize = (name) => name.replace(/_/g, " ");

function useJobNames() {
  const descriptors = useAsync(() => getJobDescriptors(), []);
  return useMemo(() => {
    const names = Object.fromEntries((descriptors.data || []).map((d) => [d.job_name, d.display_name]));
    return (job) => names[job] || humanize(job);
  }, [descriptors.data]);
}

// Every unit in the cluster with its live status. Membership comes from the
// leader's database; assignment, online state, version and running activities
// follow retained MQTT messages, so tiles update without polling.
function useCluster() {
  const { unit: self, refreshCluster } = useKiosk();
  const workers = useAsync((signal) => listWorkers(signal), []);
  const assignments = useAsync((signal) => listAssignments(signal), []);
  const jobName = useJobNames();

  const live = useTopicValues(
    [
      "pioreactor/+/$experiment/assignment",
      "pioreactor/+/$experiment/monitor/$state",
      "pioreactor/+/$experiment/monitor/versions",
    ],
    1000,
  );

  const experimentOf = useMemo(() => {
    const map = Object.fromEntries(
      (assignments.data || []).map((row) => [row.pioreactor_unit, row.experiment ?? null]),
    );
    for (const [topic, payload] of Object.entries(live)) {
      if (!topic.endsWith("/$experiment/assignment")) continue;
      const parsed = parseJson(payload);
      if (parsed && typeof parsed === "object") map[topic.split("/")[1]] = parsed.experiment ?? null;
    }
    return map;
  }, [assignments.data, live]);

  const experiments = useMemo(() => [...new Set(Object.values(experimentOf).filter(Boolean))].sort(), [experimentOf]);
  const states = useTopicValues(
    experiments.map((experiment) => `pioreactor/+/${experiment}/+/$state`),
    1000,
  );

  const units = useMemo(() => {
    const leaderVersion = parseJson(live[`pioreactor/${self}/$experiment/monitor/versions`] || "")?.app;
    return (workers.data || []).map((row) => {
      const unit = row.pioreactor_unit;
      const experiment = experimentOf[unit] ?? null;
      const monitor = live[`pioreactor/${unit}/$experiment/monitor/$state`];
      const version = parseJson(live[`pioreactor/${unit}/$experiment/monitor/versions`] || "")?.app || null;
      const prefix = `pioreactor/${unit}/${experiment}/`;
      const running = experiment
        ? Object.entries(states)
            .filter(([topic, state]) => topic.startsWith(prefix) && RUNNING_STATES.has(state))
            .map(([topic]) => jobName(topic.split("/")[3]))
            .sort()
        : [];
      return {
        unit,
        self: unit === self,
        isActive: Boolean(row.is_active),
        model: row.model_name ? `${humanize(row.model_name)} ${row.model_version}` : null,
        address: row.ipv4_address,
        experiment,
        online: monitor === undefined ? undefined : monitor === "ready" || monitor === "init" || monitor === "sleeping",
        version,
        versionDiffers: Boolean(leaderVersion && version && version !== leaderVersion),
        leaderVersion,
        running,
      };
    });
  }, [workers.data, experimentOf, live, states, self, jobName]);

  const workersReload = workers.reload;
  const assignmentsReload = assignments.reload;
  const reload = useCallback(() => {
    workersReload();
    assignmentsReload();
    refreshCluster();
  }, [workersReload, assignmentsReload, refreshCluster]);

  return { units, loaded: Boolean(workers.data), error: workers.error, reload };
}

function statusOf(row) {
  if (row.online === false) return { label: "Offline", className: "lost" };
  if (!row.isActive) return { label: "Inactive", className: "" };
  if (row.online === undefined) return null; // no monitor heard from yet
  return { label: "Online", className: "ready" };
}

const StatusBadge = ({ row }) => {
  const status = statusOf(row);
  return status && <span className={`badge ${status.className}`}>{status.label}</span>;
};

const UnitTile = memo(function UnitTile({ row, onOpen }) {
  return (
    <button
      type="button"
      className={`unit-tile ${row.online === false ? "offline" : ""}`}
      onClick={() => onOpen(row.unit)}
    >
      <span className="tile-head">
        <Icon name="pioreactor" />
        <strong className="truncate">{row.unit}</strong>
        <StatusBadge row={row} />
      </span>
      <span className="tile-exp">
        {row.experiment ? <ExperimentName name={row.experiment} /> : <span className="muted">Idle</span>}
      </span>
      <span className="sub truncate">
        {row.running.length ? row.running.join(", ") : row.experiment ? "No activities running" : " "}
      </span>
      <span className="tile-foot">
        {row.versionDiffers && <span className="badge lost">Version {row.version}</span>}
      </span>
    </button>
  );
});

/* ---------- Adding Pioreactors ---------- */

function AddUnitsSheet({ onClose, onAdded }) {
  const { leaderHostname } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const openKeyboard = useKeyboard();
  const nearby = useAsync((signal) => discoverUnits(signal), []);

  const add = async (name) => {
    const ok = await confirm({
      title: `Add ${name}?`,
      message: `${name} joins ${leaderHostname}'s cluster and restarts. It keeps its calibrations. This takes a few minutes.`,
      confirmText: "Add",
    });
    if (!ok) return;
    await addUnit(name);
    toast(`Added ${name}. It's restarting.`);
    onAdded();
    nearby.reload();
  };

  const addByName = () =>
    openKeyboard({
      label: "Pioreactor name (hostname)",
      type: "text",
      submitLabel: "Add",
      validate: validateUnitName,
      onSubmit: (raw) => add(raw.trim()).catch((error) => toast.error(error)),
    });

  const rows = nearby.data || [];

  return (
    <Sheet
      title="Add Pioreactors"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={addByName}>
            <Icon name="edit" />
            Add by name
          </button>
          <span className="grow" />
          <button type="button" className="btn" disabled={nearby.loading} onClick={nearby.reload}>
            <Icon name="refresh" />
            Search again
          </button>
        </>
      }
    >
      {nearby.loading && <Empty>Looking for Pioreactors nearby...</Empty>}
      {!nearby.loading && nearby.error && <Empty>Could not search: {nearby.error}</Empty>}
      {!nearby.loading && !nearby.error && rows.length === 0 && (
        <Empty>None found. Check that it's on and on this network, or add it by name.</Empty>
      )}
      {!nearby.loading && rows.length > 0 && (
        <div className="list">
          {rows.map((row) => (
            <div className="list-row" key={row.pioreactor_unit}>
              <Icon name="pioreactor" />
              <strong className="grow truncate">{row.pioreactor_unit}</strong>
              <AsyncButton className="btn primary" busyLabel="Adding..." onClick={() => add(row.pioreactor_unit)}>
                <Icon name="add" />
                Add
              </AsyncButton>
            </div>
          ))}
        </div>
      )}
    </Sheet>
  );
}

/* ---------- One unit ---------- */

function UnitSheet({ row, onClose, onChanged }) {
  const { leaderHostname, refreshAssignment } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const [choosing, setChoosing] = useState(false);

  const changed = (message) => {
    toast(message);
    onChanged();
    if (row.self) refreshAssignment();
  };

  const assign = async (target) => {
    if (row.experiment) {
      const ok = await confirm({
        title: `Reassign ${row.unit} to ${target}?`,
        message: `${row.unit} leaves ${row.experiment}. All its running activities stop.`,
        confirmText: "Reassign",
        danger: true,
      });
      if (!ok) return;
    }
    await assignUnit(target, row.unit);
    setChoosing(false);
    changed(`${row.unit} is in ${target}`);
  };

  const unassign = async () => {
    const ok = await confirm({
      title: `Take ${row.unit} out of ${row.experiment}?`,
      message: `${row.unit} will be idle. All its running activities stop.`,
      confirmText: "Unassign",
      danger: true,
    });
    if (!ok) return;
    await unassignUnit(row.experiment, row.unit);
    changed(`${row.unit} is idle`);
  };

  const setActive = async (active) => {
    if (active === row.isActive) return;
    if (!active) {
      const ok = await confirm({
        title: `Make ${row.unit} inactive?`,
        message: `Its running activities stop, and it won't start new ones until it's active again.`,
        confirmText: "Make inactive",
        danger: true,
      });
      if (!ok) return;
    }
    try {
      await setUnitActive(row.unit, active);
      changed(`${row.unit} is ${active ? "active" : "inactive"}`);
    } catch (error) {
      toast.error(error);
    }
  };

  const remove = async () => {
    const ok = await confirm({
      title: `Remove ${row.unit} from this cluster?`,
      message: `${row.unit} leaves ${leaderHostname}'s cluster and restarts. It keeps its calibrations and its own config. Add it again any time.`,
      confirmText: "Remove",
      danger: true,
    });
    if (!ok) return;
    await removeUnit(row.unit);
    toast(`Removed ${row.unit}. It's restarting.`);
    onChanged();
    onClose();
  };

  if (choosing) {
    return (
      <Sheet
        title={row.experiment ? `Reassign ${row.unit}` : `Assign ${row.unit}`}
        icon="experiment"
        onClose={onClose}
        footer={
          <>
            <button type="button" className="btn" onClick={() => setChoosing(false)}>
              <Icon name="back" />
              Back
            </button>
            <span className="grow" />
          </>
        }
      >
        <ExperimentList
          exclude={row.experiment}
          actionLabel={row.experiment ? "Reassign" : "Assign"}
          onPick={assign}
          emptyText="No other experiments. Create one in Experiments."
        />
      </Sheet>
    );
  }

  return (
    <Sheet title={row.unit} icon="pioreactor" onClose={onClose}>
      <div className="grid-2">
        <ReadValue label="Status" value={statusOf(row) && <StatusBadge row={row} />} />
        <ReadValue label="Model" value={row.model} />
        <ReadValue label="Software version" value={row.version} />
        <ReadValue label="Address" value={row.address} />
      </div>
      {row.versionDiffers && (
        <div className="banner">
          {row.unit} runs {row.version}; the leader runs {row.leaderVersion}. Update it from its screen or the web
          interface.
        </div>
      )}

      <h3 className="section-title">Experiment</h3>
      <div className="list">
        <div className="list-row">
          <div className="grow">
            {row.experiment ? (
              <ExperimentName name={row.experiment} className="strong" />
            ) : (
              <div className="strong">Idle</div>
            )}
            <div className="sub truncate">{row.running.length ? row.running.join(", ") : "No activities running"}</div>
          </div>
          <div className="row-actions">
            {row.experiment && (
              <AsyncButton className="btn" onClick={unassign}>
                Unassign
              </AsyncButton>
            )}
            <button type="button" className="btn primary" disabled={!row.isActive} onClick={() => setChoosing(true)}>
              {row.experiment ? "Reassign..." : "Assign..."}
            </button>
          </div>
        </div>
      </div>

      <h3 className="section-title">Cluster</h3>
      <div className="list">
        <div className="list-row">
          <div className="grow">
            <div className="strong">Active</div>
            <div className="sub">Inactive Pioreactors don't start activities.</div>
          </div>
          <Segmented
            label="Active"
            options={[
              { value: true, label: "Active" },
              { value: false, label: "Inactive" },
            ]}
            value={row.isActive}
            onChange={setActive}
          />
        </div>
        {!row.self && (
          <div className="list-row">
            <div className="grow">
              <div className="strong">Remove from cluster</div>
              <div className="sub">
                {row.experiment
                  ? "Unassign it first: Pioreactors leave between experiments."
                  : "It restarts as a standalone Pioreactor."}
              </div>
            </div>
            <AsyncButton className="btn danger" disabled={Boolean(row.experiment)} onClick={remove}>
              Remove
            </AsyncButton>
          </div>
        )}
      </div>
    </Sheet>
  );
}

function PioreactorsTab({ cluster, tabs }) {
  const [open, setOpen] = useState(null); // unit name, or "add"
  const onOpen = useCallback((name) => setOpen(name), []);
  const openRow = cluster.units.find((row) => row.unit === open);

  return (
    <>
      <div className="toolbar">{tabs}</div>
      {cluster.error && <Empty>Could not load this cluster: {cluster.error}</Empty>}
      {!cluster.loaded && !cluster.error && <Empty>Loading...</Empty>}
      {cluster.loaded && (
        <>
          <div className="tile-grid">
            {cluster.units.map((row) => (
              <UnitTile key={row.unit} row={row} onOpen={onOpen} />
            ))}
            <button type="button" className="unit-tile add" onClick={() => setOpen("add")}>
              <Icon name="add" />
              Add Pioreactors
            </button>
          </div>
        </>
      )}
      {open === "add" && <AddUnitsSheet onClose={() => setOpen(null)} onAdded={cluster.reload} />}
      {openRow && <UnitSheet row={openRow} onClose={() => setOpen(null)} onChanged={cluster.reload} />}
    </>
  );
}

/* ---------- Experiments ---------- */

function ProfilesSection({ experiment, hasUnits, onRun }) {
  const confirm = useConfirm();
  const toast = useToast();
  const { unit: self } = useKiosk();
  // Profiles run on the leader; their $state says when to re-read the list.
  const stateTopic = `pioreactor/${self}/${experiment}/experiment_profile/$state`;
  const profileState = useTopicValues([stateTopic])[stateTopic];
  const running = useAsync((signal) => listRunningProfiles(experiment, signal), [experiment, profileState]);

  const stop = async (row) => {
    const name = row.settings?.experiment_profile_name || "this profile";
    const ok = await confirm({
      title: `Stop ${name}?`,
      message: "Activities it already started keep running.",
      confirmText: "Stop profile",
      danger: true,
    });
    if (!ok) return;
    await stopProfile(row.job_id);
    toast(`Stopping ${name}...`);
  };

  return (
    <>
      <h3 className="section-title">Profile</h3>
      <div className="list">
        {(running.data || []).map((row) => (
          <div className="list-row" key={row.job_id}>
            <span className="grow">
              <span className="strong truncate">{row.settings?.experiment_profile_name || "Profile"}</span>
              <span className="sub">Running</span>
            </span>
            <AsyncButton className="btn danger" onClick={() => stop(row)}>
              <Icon name="stop" />
              Stop
            </AsyncButton>
          </div>
        ))}
        <button type="button" className="list-row add-row" disabled={!hasUnits} onClick={onRun}>
          <Icon name="profile" />
          <span className="grow">{hasUnits ? "Run a profile..." : "Assign Pioreactors to run a profile"}</span>
          <Icon name="forward" />
        </button>
      </div>
    </>
  );
}

function ProfilePickerSheet({ experiment, onBack, onClose }) {
  const confirm = useConfirm();
  const toast = useToast();
  const profiles = useAsync((signal) => listProfiles(signal), []);
  const rows = profiles.data || [];

  const run = async (profile) => {
    const name = profile.experimentProfile?.experiment_profile_name || profile.file;
    const ok = await confirm({
      title: `Run ${name}?`,
      message: `It runs in ${experiment}, on the Pioreactors assigned to it.`,
      confirmText: "Run profile",
    });
    if (!ok) return;
    await runProfile(profile.file, experiment);
    toast(`Started ${name}`);
    onBack();
  };

  return (
    <Sheet
      title={`Run a profile in ${experiment}`}
      icon="profile"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onBack}>
            <Icon name="back" />
            Back
          </button>
          <span className="grow" />
        </>
      }
    >
      {profiles.loading && <Empty>Loading profiles...</Empty>}
      {profiles.error && <Empty>Could not load profiles: {profiles.error}</Empty>}
      {profiles.data && rows.length === 0 && <Empty>No profiles yet. Write one in the web interface.</Empty>}
      {rows.length > 0 && (
        <div className="list">
          {rows.map((profile) => (
            <div className="list-row" key={profile.file}>
              <div className="grow">
                <div className="strong truncate">
                  {profile.experimentProfile?.experiment_profile_name || profile.file}
                </div>
                <div className="sub truncate">{profile.experimentProfile?.metadata?.description || profile.file}</div>
              </div>
              <AsyncButton className="btn primary" onClick={() => run(profile)}>
                Run
              </AsyncButton>
            </div>
          ))}
        </div>
      )}
    </Sheet>
  );
}

function AssignUnitsSheet({ experiment, units, onBack, onDone, onClose }) {
  const confirm = useConfirm();
  const toast = useToast();
  const candidates = units.filter((row) => row.experiment !== experiment && row.isActive);
  const [picked, setPicked] = useState(
    () => new Set(candidates.filter((row) => !row.experiment).map((row) => row.unit)),
  );

  const toggle = (unit) =>
    setPicked((previous) => {
      const next = new Set(previous);
      if (next.has(unit)) next.delete(unit);
      else next.add(unit);
      return next;
    });

  const submit = async () => {
    const chosen = candidates.filter((row) => picked.has(row.unit));
    const moving = chosen.filter((row) => row.experiment);
    if (moving.length) {
      const ok = await confirm({
        title: `Reassign ${plural(moving.length, "Pioreactor")} to ${experiment}?`,
        message: `${moving.map((row) => `${row.unit} leaves ${row.experiment}`).join("; ")}. Their running activities stop.`,
        confirmText: "Reassign",
        danger: true,
      });
      if (!ok) return;
    }
    for (const row of chosen) {
      await assignUnit(experiment, row.unit);
    }
    toast(`Assigned ${chosen.map((row) => row.unit).join(", ")}`);
    onDone();
  };

  return (
    <Sheet
      title={`Assign to ${experiment}`}
      icon="experiment"
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn" onClick={onBack}>
            <Icon name="back" />
            Back
          </button>
          <span className="grow" />
          {candidates.length > 0 && (
            <AsyncButton className="btn primary" disabled={picked.size === 0} onClick={submit}>
              {picked.size ? `Assign ${plural(picked.size, "Pioreactor")}` : "Assign"}
            </AsyncButton>
          )}
        </>
      }
    >
      {candidates.length === 0 ? (
        <Empty>Every active Pioreactor is already in {experiment}.</Empty>
      ) : (
        <div className="list">
          {candidates.map((row) => (
            <button
              type="button"
              key={row.unit}
              className={`list-row pick ${picked.has(row.unit) ? "on" : ""}`}
              aria-pressed={picked.has(row.unit)}
              onClick={() => toggle(row.unit)}
            >
              <span className="check">{picked.has(row.unit) && <Icon name="check" />}</span>
              <span className="grow">
                <span className="strong truncate">{row.unit}</span>
                {row.experiment ? (
                  <ExperimentName name={row.experiment} className="sub" />
                ) : (
                  <span className="sub">Idle</span>
                )}
              </span>
              {row.online === false && <span className="badge lost">Offline</span>}
            </button>
          ))}
        </div>
      )}
    </Sheet>
  );
}

function ExperimentDetailSheet({ experiment, units, onClose, onChanged }) {
  const { refreshAssignment } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const [mode, setMode] = useState(null); // null, "assign" or "profile"
  const members = units.filter((row) => row.experiment === experiment);

  const changed = (message) => {
    if (message) toast(message);
    onChanged();
    refreshAssignment();
  };

  const unassign = async (row) => {
    const ok = await confirm({
      title: `Take ${row.unit} out of ${experiment}?`,
      message: `${row.unit} will be idle. All its running activities stop.`,
      confirmText: "Unassign",
      danger: true,
    });
    if (!ok) return;
    await unassignUnit(experiment, row.unit);
    changed(`${row.unit} is idle`);
  };

  const end = async () => {
    const ok = await confirm({
      title: `End ${experiment}?`,
      message: `This stops all activities and unassigns ${members.length ? `every Pioreactor in it (${members.map((row) => row.unit).join(", ")})` : "every Pioreactor in it"}. Its data is kept.`,
      confirmText: "End experiment",
      danger: true,
    });
    if (!ok) return;
    await endExperiment(experiment);
    changed(`Ended ${experiment}`);
    onClose();
  };

  if (mode === "assign") {
    return (
      <AssignUnitsSheet
        experiment={experiment}
        units={units}
        onClose={onClose}
        onBack={() => setMode(null)}
        onDone={() => {
          setMode(null);
          changed();
        }}
      />
    );
  }
  if (mode === "profile") {
    return <ProfilePickerSheet experiment={experiment} onClose={onClose} onBack={() => setMode(null)} />;
  }

  return (
    <Sheet
      title={experiment}
      icon="experiment"
      onClose={onClose}
      footer={
        <>
          <AsyncButton className="btn danger" disabled={members.length === 0} onClick={end}>
            End experiment
          </AsyncButton>
          <span className="grow" />
        </>
      }
    >
      <h3 className="section-title">Pioreactors</h3>
      <div className="list">
        {members.map((row) => (
          <div className="list-row" key={row.unit}>
            <div className="grow">
              <div className="strong truncate">
                {row.unit}
              </div>
              <div className="sub truncate">
                {row.running.length ? row.running.join(", ") : "No activities running"}
              </div>
            </div>
            {row.online === false && <span className="badge lost">Offline</span>}
            <AsyncButton className="btn" onClick={() => unassign(row)}>
              Unassign
            </AsyncButton>
          </div>
        ))}
        <button type="button" className="list-row add-row" onClick={() => setMode("assign")}>
          <Icon name="add" />
          <span className="grow">Assign Pioreactors...</span>
          <Icon name="forward" />
        </button>
      </div>
      <ProfilesSection experiment={experiment} hasUnits={members.length > 0} onRun={() => setMode("profile")} />
    </Sheet>
  );
}

const ExperimentRow = memo(function ExperimentRow({ experiment, subtitle, onOpen }) {
  return (
    <button type="button" className="list-row" onClick={() => onOpen(experiment)}>
      <span className="grow">
        <ExperimentName name={experiment} className="strong" />
        <span className="sub truncate">{subtitle}</span>
      </span>
      <Icon name="forward" />
    </button>
  );
});

function ExperimentsTab({ cluster, tabs }) {
  const [version, setVersion] = useState(0);
  const experiments = useAsync((signal) => listExperiments(signal), [version]);
  const [open, setOpen] = useState(null);
  const onOpen = useCallback((experiment) => setOpen(experiment), []);

  const create = useCreateExperiment((name) => {
    setVersion((v) => v + 1);
    setOpen(name);
  });

  const unitsIn = useMemo(() => {
    const map = {};
    for (const row of cluster.units) {
      if (row.experiment) (map[row.experiment] ||= []).push(row.unit);
    }
    return map;
  }, [cluster.units]);

  const rows = experiments.data || [];
  const inProgress = rows.filter((row) => unitsIn[row.experiment]);
  const others = rows.filter((row) => !unitsIn[row.experiment]);

  return (
    <>
      <div className="toolbar">
        {tabs}
        <span className="grow" />
        <button type="button" className="btn primary" onClick={create}>
          <Icon name="add" />
          New experiment
        </button>
      </div>
      {experiments.error && <Empty>Could not load experiments: {experiments.error}</Empty>}
      {!experiments.data && !experiments.error && <Empty>Loading experiments...</Empty>}
      {experiments.data && (
        <>
          <h2 className="section-title">In progress</h2>
          {inProgress.length === 0 ? (
            <p className="muted">No Pioreactor is in an experiment.</p>
          ) : (
            <div className="list">
              {inProgress.map((row) => (
                <ExperimentRow
                  key={row.experiment}
                  experiment={row.experiment}
                  subtitle={unitsIn[row.experiment].join(", ")}
                  onOpen={onOpen}
                />
              ))}
            </div>
          )}
          {others.length > 0 && (
            <>
              <h2 className="section-title">Other experiments</h2>
              <div className="list">
                {others.map((row) => (
                  <ExperimentRow
                    key={row.experiment}
                    experiment={row.experiment}
                    subtitle={formatDate(row.created_at)}
                    onOpen={onOpen}
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}
      {open && (
        <ExperimentDetailSheet
          experiment={open}
          units={cluster.units}
          onClose={() => setOpen(null)}
          onChanged={() => {
            cluster.reload();
            setVersion((v) => v + 1);
          }}
        />
      )}
    </>
  );
}

export default function Cluster() {
  const page = usePage();
  const tab = page === "experiments" ? "experiments" : "cluster";
  const cluster = useCluster();

  const tabs = <Segmented label="Cluster section" options={TABS} value={tab} onChange={navigate} />;

  return (
    <div className="content">
      {tab === "cluster" ? (
        <PioreactorsTab cluster={cluster} tabs={tabs} />
      ) : (
        <ExperimentsTab cluster={cluster} tabs={tabs} />
      )}
    </div>
  );
}
