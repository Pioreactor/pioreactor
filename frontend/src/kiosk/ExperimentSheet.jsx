import { useState } from "react";
import { useKiosk } from "./context";
import { useAsync } from "./hooks";
import {
  assignUnit,
  createExperiment,
  endExperiment,
  formatDate,
  listExperiments,
  listUnitsIn,
  unassignUnit,
  validateExperimentName,
} from "./cluster";
import { Icon } from "./icons";
import { useKeyboard } from "./Keyboard";
import { AsyncButton, Empty, ExperimentName, ReadValue, Sheet, useConfirm, useToast } from "./ui";

export function ExperimentList({ exclude, actionLabel, onPick, emptyText }) {
  const experiments = useAsync((signal) => listExperiments(signal), []);
  const rows = (experiments.data || []).filter((row) => row.experiment !== exclude);

  if (experiments.error) return <Empty>Could not load experiments: {experiments.error}</Empty>;
  if (!experiments.data) return <Empty>Loading experiments...</Empty>;
  if (rows.length === 0) return <Empty>{emptyText}</Empty>;

  return (
    <div className="list">
      {rows.map((row) => (
        <div className="list-row" key={row.experiment}>
          <div className="grow">
            <ExperimentName name={row.experiment} className="strong" />
            <div className="sub">{formatDate(row.created_at)}</div>
          </div>
          <AsyncButton className="btn primary" onClick={() => onPick(row.experiment)}>
            {actionLabel}
          </AsyncButton>
        </div>
      ))}
    </div>
  );
}

// Asks for a name, creates the experiment on the leader, then calls onCreated(name).
export function useCreateExperiment(onCreated) {
  const openKeyboard = useKeyboard();
  const toast = useToast();
  return () =>
    openKeyboard({
      label: "New experiment name",
      type: "text",
      submitLabel: "Create",
      validate: validateExperimentName,
      onSubmit: async (raw) => {
        const name = raw.trim();
        try {
          await createExperiment(name);
          await onCreated(name);
        } catch (error) {
          toast.error(error);
        }
      },
    });
}

// This unit's experiment: join, reassign, leave. Every screen can do that (KIOSK.md).
// Only leaders' screens create and end experiments; there, "New experiment"
// also assigns this unit, since it was asked from this unit's experiment chip.
export default function ExperimentSheet({ onClose }) {
  const { unit, role, isLeader, leaderHostname, leaderReachable, experiment, experimentMetadata, worker, refreshAssignment } =
    useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const [choosing, setChoosing] = useState(false);
  // Fetched up front so the End confirmation opens instantly.
  const members = useAsync(isLeader && experiment ? (signal) => listUnitsIn(experiment, signal) : null, [isLeader, experiment]);

  const done = (message) => {
    toast(message);
    refreshAssignment();
    onClose();
  };

  const assign = async (target) => {
    const moving = Boolean(experiment);
    const ok = await confirm(
      moving
        ? {
            title: `Reassign ${unit} to ${target}?`,
            message: `${unit} leaves ${experiment}. All its running activities stop.`,
            confirmText: "Reassign",
            danger: true,
          }
        : {
            title: `Join ${target}?`,
            message: `${unit} will be assigned to this experiment.`,
            confirmText: "Join",
          },
    );
    if (!ok) return;
    await assignUnit(target, unit);
    done(moving ? `Reassigned to ${target}` : `Joined ${target}`);
  };

  const createAndJoin = useCreateExperiment(async (name) => {
    await assignUnit(name, unit);
    done(`Created ${name}`);
  });

  const leave = async () => {
    const ok = await confirm({
      title: `Leave ${experiment}?`,
      message: `${unit} will be unassigned. All its running activities stop.`,
      confirmText: "Leave experiment",
      danger: true,
    });
    if (!ok) return;
    await unassignUnit(experiment, unit);
    done(`Left ${experiment}`);
  };

  const end = async () => {
    const units = (members.data || []).map((row) => row.pioreactor_unit);
    const ok = await confirm({
      title: `End ${experiment}?`,
      message: `This stops all activities and unassigns ${units.length ? `every Pioreactor in it (${units.join(", ")})` : "every Pioreactor in it"}. Its data is kept.`,
      confirmText: "End experiment",
      danger: true,
    });
    if (!ok) return;
    await endExperiment(experiment);
    done(`Ended ${experiment}`);
  };

  if (role === "worker" && leaderReachable === false) {
    return (
      <Sheet title="Experiment" icon="experiment" onClose={onClose}>
        <div className="banner">
          Can't reach the leader, {leaderHostname}. Joining or leaving an experiment needs it. Activities here keep running.
        </div>
        {experiment && <ReadValue label="Assigned to" value={<ExperimentName name={experiment} />} />}
      </Sheet>
    );
  }

  if (worker === null) {
    return (
      <Sheet title="Experiment" icon="experiment" onClose={onClose}>
        <div className="banner">
          {isLeader
            ? `${unit} isn't one of this cluster's Pioreactors, so it can't join experiments.`
            : `${leaderHostname} doesn't list ${unit}. Add it again from the leader's screen or web interface.`}
        </div>
      </Sheet>
    );
  }

  if (experiment === undefined) {
    return (
      <Sheet title="Experiment" icon="experiment" onClose={onClose}>
        <Empty>Waiting for the leader...</Empty>
      </Sheet>
    );
  }

  if (experiment === null || choosing) {
    return (
      <Sheet
        title={experiment ? "Reassign to another experiment" : "Join an experiment"}
        icon="experiment"
        onClose={onClose}
        footer={
          experiment || isLeader ? (
            <>
              {experiment && (
                <button type="button" className="btn" onClick={() => setChoosing(false)}>
                  <Icon name="back" />
                  Back to {experiment}
                </button>
              )}
              <span className="grow" />
              {isLeader && !experiment && (
                <button type="button" className="btn primary" onClick={createAndJoin}>
                  <Icon name="add" />
                  New experiment
                </button>
              )}
            </>
          ) : null
        }
      >
        {!experiment && (
          <p className="muted">
            {role === "standalone"
              ? `Start a new experiment, or continue one from before.`
              : `${unit} isn't in an experiment. Choose one to join.`}
          </p>
        )}
        <ExperimentList
          exclude={experiment}
          actionLabel={experiment ? "Reassign" : "Join"}
          onPick={assign}
          emptyText={
            isLeader
              ? "No other experiments. Create one with New experiment."
              : "No other experiments. Create one on the leader's screen or web interface."
          }
        />
      </Sheet>
    );
  }

  return (
    <Sheet
      title="Experiment"
      icon="experiment"
      onClose={onClose}
      footer={
        <>
          {isLeader && (
            <AsyncButton className="btn danger" onClick={end}>
              End experiment
            </AsyncButton>
          )}
          <span className="grow" />
          {role !== "standalone" && (
            <>
              <AsyncButton className="btn" onClick={leave}>
                Leave
              </AsyncButton>
              <button type="button" className="btn primary" onClick={() => setChoosing(true)}>
                Reassign...
              </button>
            </>
          )}
        </>
      }
    >
      <div className="grid-2">
        <ReadValue label="Assigned to" value={<ExperimentName name={experiment} />} />
        <ReadValue label="Started" value={formatDate(experimentMetadata?.created_at)} />
      </div>
      {experimentMetadata?.description && <p className="description">{experimentMetadata.description}</p>}
    </Sheet>
  );
}
