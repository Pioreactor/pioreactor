import { useState } from "react";
import { enc, unitApi } from "../api";
import { useKiosk } from "../context";
import { Icon } from "../icons";
import { EditField } from "../Keyboard";
import { useJobControl } from "../jobs";
import { AsyncButton, ReadValue, StateBadge, useToast } from "../ui";
import { getBioreactorConfirmedValue } from "../../utils/bioreactor";
import { fmt, RUNNING_STATES } from "../values";

const PUMPS = [
  { job: "add_media", title: "Add media", verb: "Add" },
  { job: "remove_waste", title: "Remove waste", verb: "Remove" },
  { job: "add_alt_media", title: "Add alt. media", verb: "Add" },
];

const VOLUME_PRESETS = [0.5, 1, 2, 5, 10];

function PumpCard({ pump, state }) {
  const toast = useToast();
  const control = useJobControl();
  const [ml, setMl] = useState(1);
  const running = RUNNING_STATES.has(state);

  // The unit refuses additions that would overfill the vial (400 with a reason).
  const run = async () => {
    await control.run(pump.job, { options: { ml, source_of_event: "UI" } });
    toast(`${pump.title}: ${fmt(ml)} mL`);
  };

  return (
    <div className="card">
      <h3>
        {pump.title}
        {running && <StateBadge state="ready" pending="Running" />}
      </h3>
      <EditField
        className="wide"
        label="Volume"
        value={ml}
        unit="mL"
        min={0.01}
        allowNegative={false}
        presets={VOLUME_PRESETS}
        onCommit={setMl}
      />
      {running ? (
        <AsyncButton className="btn danger solid block" onClick={() => control.stop(pump.job)}>
          <Icon name="stop" />
          Stop pump
        </AsyncButton>
      ) : (
        <AsyncButton className="btn primary block" onClick={run}>
          {pump.verb} {fmt(ml)} mL
        </AsyncButton>
      )}
    </div>
  );
}

// A tab of Activities, which handles the no-experiment and offline cases.
export default function Dosing({ get }) {
  const { config, experiment } = useKiosk();
  const bio = (key) => getBioreactorConfirmedValue({ [key]: get("bioreactor", key) }, config, key);
  const setBio = (key) => (value) =>
    unitApi(`/bioreactor/experiments/${enc(experiment)}`, { method: "PATCH", body: { values: { [key]: value } } });

  return (
    <>
      <h2 className="section-title">Vial</h2>
      <div className="grid-4">
        <EditField label="Current volume" value={fmt(bio("current_volume_ml"))} unit="mL" min={0} allowNegative={false} onCommit={setBio("current_volume_ml")} />
        <EditField label="Efflux tube level" value={fmt(bio("efflux_tube_volume_ml"))} unit="mL" min={0} allowNegative={false} onCommit={setBio("efflux_tube_volume_ml")} />
        <ReadValue label="Alt. media fraction" value={fmt(bio("alt_media_fraction"))} />
        <ReadValue
          label="Added / removed"
          value={`${fmt(bio("cumulative_media_added_ml")) ?? "0"} / ${fmt(bio("cumulative_waste_removed_ml")) ?? "0"}`}
          unit="mL"
        />
      </div>
      <h2 className="section-title">Pumps</h2>
      <div className="grid-3">
        {PUMPS.map((pump) => (
          <PumpCard key={pump.job} pump={pump} state={get(pump.job, "$state")} />
        ))}
      </div>
    </>
  );
}
