import { useState } from "react";
import { useDisplay } from "../context";
import Header from "../Header";
import { useJSON } from "../hooks";
import { AsyncButton, Icon, ReadValue, Segmented, useConfirm, useToast } from "../ui";
import { applyTheme, readTheme } from "../theme";

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function PowerButtons({ unit, label }) {
  const confirm = useConfirm();
  const toast = useToast();
  const isAll = unit === "$broadcast";

  const send = async (action) => {
    const verb = action === "reboot" ? "Reboot" : "Shut down";
    const ok = await confirm({
      title: `${verb} ${label}?`,
      message:
        action === "shutdown"
          ? "Running activities stop. You'll need to unplug and replug power to start it again."
          : "Running activities stop while it restarts.",
      confirmText: verb,
      danger: true,
    });
    if (!ok) return;
    const response = await fetch(`/api/units/${unit}/system/${action}`, { method: "POST" });
    if (!response.ok) throw new Error(`Could not ${verb.toLowerCase()} ${label}.`);
    toast(`${verb === "Reboot" ? "Rebooting" : "Shutting down"} ${label}...`);
  };

  return (
    <>
      <AsyncButton className={`btn small ${isAll ? "" : "ghost"}`} onClick={() => send("reboot")}>
        <Icon name="refresh" />
        {isAll ? "Reboot all" : "Reboot"}
      </AsyncButton>
      <AsyncButton className="btn small danger" onClick={() => send("shutdown")}>
        {isAll ? "Shut down all" : "Shut down"}
      </AsyncButton>
    </>
  );
}

export default function System() {
  const { leader, labelFor } = useDisplay();
  const [theme, setTheme] = useState(readTheme);
  const version = useJSON("/unit_api/versions/app");
  const ip = useJSON("/unit_api/system/ipv4");
  const units = useJSON("/api/units");
  const address = ip.data?.ipv4_address || `${leader || window.location.hostname}.local`;

  const chooseTheme = (mode) => {
    applyTheme(mode);
    setTheme(mode);
  };

  const sortedUnits = [...(units.data || [])]
    .map((row) => row.pioreactor_unit)
    .sort((a, b) => (a === leader ? -1 : b === leader ? 1 : a.localeCompare(b, undefined, { numeric: true })));

  return (
    <>
      <Header title="System" />
      <div className="content">
        <div className="section-title">Leader</div>
        <div className="grid-3">
          <ReadValue label="Hostname" value={leader} />
          <ReadValue label="Address" value={ip.data?.ipv4_address || "—"} />
          <ReadValue label="Software version" value={version.data?.version} />
        </div>
        <p className="description" style={{ marginTop: "0.5rem" }}>
          Calibrations, plugins, configuration, data exports and updates are in the full web interface. On a computer on the
          same network, open <strong>http://{address}/</strong>
        </p>

        <div className="section-title">Display</div>
        <div className="btn-row" style={{ alignItems: "center" }}>
          <span className="muted" style={{ fontSize: "0.9rem" }}>Appearance</span>
          <Segmented options={THEMES} value={theme} onChange={chooseTheme} />
          <button className="btn" style={{ marginLeft: "auto" }} onClick={() => window.location.reload()}>
            <Icon name="refresh" />
            Reload display
          </button>
        </div>

        <div className="section-title">Power</div>
        <div className="list">
          {sortedUnits.map((unit) => (
            <div className="list-row" key={unit}>
              <div className="grow truncate">
                {labelFor(unit) !== unit ? `${labelFor(unit)} (${unit})` : unit}
                {unit === leader && <span className="sub"> · leader, runs this display</span>}
              </div>
              <PowerButtons unit={unit} label={unit} />
            </div>
          ))}
          {sortedUnits.length > 1 && (
            <div className="list-row">
              <div className="grow">All Pioreactors</div>
              <PowerButtons unit="$broadcast" label="all Pioreactors" />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
