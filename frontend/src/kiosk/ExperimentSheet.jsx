import { useState } from "react";
import { useKiosk } from "./context";
import { useAsync } from "./hooks";
import { enc, leaderApi } from "./api";
import { Icon } from "./icons";
import { useKeyboard } from "./Keyboard";
import { AsyncButton, Empty, ReadValue, Sheet, useConfirm, useToast } from "./ui";

function formatDate(timestamp) {
  const ms = Date.parse(timestamp);
  return Number.isFinite(ms) ? new Date(ms).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : null;
}

const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

// The leader's own rules (api.py _validate_experiment_name), checked before sending.
function validateExperimentName(raw) {
  const name = raw.trim();
  if (!name) return "Enter a name.";
  if (name.length >= 200) return "Use fewer than 200 characters.";
  if (name.toLowerCase() === "current") return "\"current\" is reserved. Choose another name.";
  if (name.startsWith("_testing")) return "Names can't start with \"_testing\".";
  if (/[#$%+/?\\]/.test(name)) return "Names can't contain # $ % + / ? or \\.";
  return null;
}


function ExperimentList({ exclude, actionLabel, onPick }) {
  const experiments = useAsync((signal) => leaderApi("/experiments", { signal }), []);
  const rows = (experiments.data || []).filter((row) => row.experiment !== exclude);

  if (experiments.error) return <Empty>Could not load experiments: {experiments.error}</Empty>;
  if (!experiments.data) return <Empty>Loading experiments...</Empty>;
  if (rows.length === 0) return <Empty>No other experiments. Create one in the main web interface.</Empty>;

  return (
    <div className="list">
      {rows.map((row) => (
        <div className="list-row" key={row.experiment}>
          <div className="grow">
            <div className="truncate strong">{row.experiment}</div>
            <div className="sub">
              {formatDate(row.created_at)} · {plural(row.worker_count, "Pioreactor")}
            </div>
          </div>
          <AsyncButton className="btn primary" onClick={() => onPick(row.experiment)}>
            {actionLabel}
          </AsyncButton>
        </div>
      ))}
    </div>
  );
}

// Assignment for this unit: join, move, leave. Only the leader's screen can end
// an experiment, since that stops and unassigns every unit in it.
export default function ExperimentSheet({ onClose }) {
  const { unit, isLeader, experiment, experimentMetadata, worker, refreshAssignment } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const openKeyboard = useKeyboard();
  const [choosing, setChoosing] = useState(false);
  const [listVersion, setListVersion] = useState(0);
  // Fetched up front so the leader's End confirmation opens instantly.
  const members = useAsync(
    isLeader && experiment ? (signal) => leaderApi(`/experiments/${enc(experiment)}/workers`, { signal }) : null,
    [isLeader, experiment],
  );

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
            message: `${unit} leaves ${experiment}. All running jobs will be stopped.`,
            confirmText: `Reassign`,
            danger: true,
          }
        : {
            title: `Assign to ${target}?`,
            message: `${unit} will be assigned to this experiment.`,
            confirmText: "Assign",
          },
    );
    if (!ok) return;
    await leaderApi(`/experiments/${enc(target)}/workers`, { method: "PUT", body: { pioreactor_unit: unit } });
    done(moving ? `Reassigned to ${target}` : `Assigned to ${target}`);
  };

  // Leader's screen only. Creating doesn't assign anything: the new experiment
  // appears in the list, to assign from there like any other.
  const createExperiment = () =>
    openKeyboard({
      label: "New experiment name",
      type: "text",
      submitLabel: "Create",
      validate: validateExperimentName,
      onSubmit: async (raw) => {
        const name = raw.trim();
        try {
          await leaderApi("/experiments", { method: "POST", body: { experiment: name } });
          toast(`Created ${name}`);
          setListVersion((v) => v + 1);
        } catch (error) {
          toast.error(error);
        }
      },
    });

  const leave = async () => {
    const ok = await confirm({
      title: `Unassign from ${experiment}?`,
      message: `${unit} will be unassigned. All running jobs will be stopped.`,
      confirmText: "Unassign",
      danger: true,
    });
    if (!ok) return;
    await leaderApi(`/experiments/${enc(experiment)}/workers/${enc(unit)}`, { method: "DELETE" });
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
    await leaderApi(`/experiments/${enc(experiment)}/workers`, { method: "DELETE" });
    done(`Ended ${experiment}`);
  };

  if (worker === null) {
    return (
      <Sheet title="Experiment" onClose={onClose}>
        <div className="banner">{unit} isn't in the leader's inventory. Add it from the main web interface first.</div>
      </Sheet>
    );
  }

  if (experiment === undefined) {
    return (
      <Sheet title="Experiment" onClose={onClose}>
        <Empty>Waiting for the leader...</Empty>
      </Sheet>
    );
  }

  if (experiment === null || choosing) {
    return (
      <Sheet
        title={experiment ? "Reassign to another experiment" : "Assign to an experiment"}
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
              {isLeader && (
                <button type="button" className="btn primary" onClick={createExperiment}>
                  <Icon name="add" />
                  New experiment
                </button>
              )}
            </>
          ) : null
        }
      >
        {!experiment && <p className="muted">{unit} isn't assigned to an experiment. Choose one to join.</p>}
        <ExperimentList key={listVersion} exclude={experiment} actionLabel={"Assign"} onPick={assign} />
      </Sheet>
    );
  }

  return (
    <Sheet
      title="Experiment"
      onClose={onClose}
      footer={
        <>
          {isLeader && (
            <AsyncButton className="btn danger" onClick={end}>
              End experiment
            </AsyncButton>
          )}
          <span className="grow" />
          <AsyncButton className="btn danger" onClick={leave}>
            Unassign
          </AsyncButton>
          <button type="button" className="btn primary" onClick={() => setChoosing(true)}>
            Reassign
          </button>
        </>
      }
    >
      <div className="grid-2">
        <ReadValue label="Assigned to" value={experiment} />
        <ReadValue label="Started" value={formatDate(experimentMetadata?.created_at)} />
      </div>
      {experimentMetadata?.description && <p className="description">{experimentMetadata.description}</p>}
    </Sheet>
  );
}
