import { useEffect, useState } from "react";
import { useDisplay } from "../context";
import { AsyncButton, Icon, ReadValue, StateBadge, useToast } from "../ui";
import { EditField } from "../Keyboard";
import { fmt } from "../values";
import { runPioreactorJob } from "../../utils/jobs";
import { getBioreactorConfirmedValue, updateBioreactorValues } from "../../utils/bioreactor";
import { experimentPathSegment } from "../../utils/url";

const PUMPS = [
  { job: "add_media", title: "Add media", verb: "Add" },
  { job: "remove_waste", title: "Remove waste", verb: "Remove" },
  { job: "add_alt_media", title: "Add alt. media", verb: "Add" },
];

const VOLUME_PRESETS = [0.5, 1, 2, 5, 10];

function PumpCard({ unit, experiment, pump, state, currentVolume, maxVolume }) {
  const toast = useToast();
  const [ml, setMl] = useState(1);
  const running = state === "ready" || state === "init";
  const isAdd = pump.job.startsWith("add");

  const run = async () => {
    if (isAdd && maxVolume !== null && currentVolume !== null && currentVolume + ml > maxVolume) {
      throw new Error(`Adding ${ml} mL would exceed the vial's ${maxVolume} mL limit.`);
    }
    await runPioreactorJob(unit, experiment, pump.job, [], { ml, source_of_event: "UI" });
    toast(`${pump.title}: ${ml} mL`);
  };

  const stop = async () => {
    const response = await fetch(`/api/workers/${unit}/jobs/stop/job_name/${pump.job}/experiments/${experimentPathSegment(experiment)}`, {
      method: "POST",
    });
    if (!response.ok) throw new Error("Failed to stop the pump. Try again!");
  };

  return (
    <div className="card action-card">
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
        <AsyncButton className="btn danger solid block" onClick={stop}>
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

export default function DosingPanel({ unit, experiment, get }) {
  const { config } = useDisplay();
  const [model, setModel] = useState(null);

  useEffect(() => {
    let ignore = false;
    fetch(`/api/workers/${unit}/model`)
      .then((response) => (response.ok ? response.json() : null))
      .then((data) => !ignore && setModel(data))
      .catch(() => {});
    return () => {
      ignore = true;
    };
  }, [unit]);

  const bio = (key) => getBioreactorConfirmedValue({ [key]: get("bioreactor", key) }, config, key);
  const currentVolume = bio("current_volume_ml");
  const maxVolume = Number.isFinite(model?.reactor_max_fill_volume_ml) ? model.reactor_max_fill_volume_ml : null;
  const setBio = (key) => (value) => updateBioreactorValues(unit, experiment, { [key]: value });

  return (
    <>
      <div className="section-title">Vial</div>
      <div className="grid-4">
        <EditField
          label="Current volume"
          value={fmt(currentVolume)}
          unit="mL"
          min={0}
          max={maxVolume ?? undefined}
          allowNegative={false}
          onCommit={setBio("current_volume_ml")}
        />
        <EditField
          label="Efflux tube level"
          value={fmt(bio("efflux_tube_volume_ml"))}
          unit="mL"
          min={0}
          max={maxVolume ?? undefined}
          allowNegative={false}
          onCommit={setBio("efflux_tube_volume_ml")}
        />
        <ReadValue label="Alt. media fraction" value={fmt(bio("alt_media_fraction"))} />
        <ReadValue
          label="Added / removed"
          value={`${fmt(bio("cumulative_media_added_ml")) ?? "0"} / ${fmt(bio("cumulative_waste_removed_ml")) ?? "0"}`}
          unit="mL"
        />
      </div>
      <div className="section-title">Pumps</div>
      <div className="grid-3">
        {PUMPS.map((pump) => (
          <PumpCard
            key={pump.job}
            unit={unit}
            experiment={experiment}
            pump={pump}
            state={get(pump.job, "$state")}
            currentVolume={currentVolume}
            maxVolume={maxVolume}
          />
        ))}
      </div>
    </>
  );
}
