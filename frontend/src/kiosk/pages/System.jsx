import { useState } from "react";
import { unitApi } from "../api";
import { useKiosk } from "../context";
import { useAsync, useBrokerConnected } from "../hooks";
import { Icon } from "../icons";
import { applyTheme, readTheme } from "../theme";
import { AsyncButton, ReadValue, Segmented, useConfirm, useToast } from "../ui";

const THEMES = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return null;
  const gb = bytes / 1024 ** 3;
  return gb >= 1 ? `${gb.toFixed(1)} GB` : `${Math.round(bytes / 1024 ** 2)} MB`;
}

function usage(data) {
  if (!data) return null;
  return `${formatBytes(data.available_bytes)} free of ${formatBytes(data.total_bytes)}`;
}

function PowerButtons() {
  const { unit } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();

  const send = async (action) => {
    const verb = action === "reboot" ? "Reboot" : "Shut down";
    const ok = await confirm({
      title: `${verb} ${unit}?`,
      message:
        action === "shutdown"
          ? "Running activities stop. You'll need to unplug and replug power to start it again."
          : "Running activities stop while it restarts.",
      confirmText: verb,
      danger: true,
    });
    if (!ok) return;
    await unitApi(`/system/${action}`, { method: "POST" });
    toast(action === "reboot" ? `Rebooting ${unit}...` : `Shutting down ${unit}...`);
  };

  return (
    <div className="btn-row">
      <AsyncButton className="btn" onClick={() => send("reboot")}>
        <Icon name="restart" />
        Reboot
      </AsyncButton>
      <AsyncButton className="btn danger" onClick={() => send("shutdown")}>
        <Icon name="power" />
        Shut down
      </AsyncButton>
    </div>
  );
}

export default function System() {
  const { unit, leaderHostname, isLeader, config } = useKiosk();
  const connected = useBrokerConnected();
  const [theme, setTheme] = useState(readTheme);
  const version = useAsync((signal) => unitApi("/versions/app", { signal }), []);
  const ip = useAsync((signal) => unitApi("/system/ipv4", { signal }), []);
  const disk = useAsync((signal) => unitApi("/system/disk_space", { signal }), [], { refreshMs: 60000 });
  const memory = useAsync((signal) => unitApi("/system/memory", { signal }), [], { refreshMs: 60000 });
  const leaderAddress = config["cluster.topology"]?.leader_address || leaderHostname;

  const chooseTheme = (mode) => {
    applyTheme(mode);
    setTheme(mode);
  };

  return (
    <div className="content">
      <div className="grid-3">
        <ReadValue label="Name" value={unit} />
        <ReadValue label="Address" value={ip.data?.ipv4_address} />
        <ReadValue label="Software version" value={version.data?.version} />
        <ReadValue label="Storage" value={usage(disk.data)} />
        <ReadValue label="Memory" value={usage(memory.data)} />
        {!isLeader && <ReadValue label="Leader" value={`${leaderHostname}${connected ? "" : " (unreachable)"}`} />}
      </div>
      <p className="description spaced">
        Plugins, configuration, data exports and updates are in the main web interface. On a computer on the same
        network, open <strong>http://{leaderAddress}/</strong>
      </p>

      <h2 className="section-title">Screen</h2>
      <div className="btn-row">
        <Segmented label="Appearance" options={THEMES} value={theme} onChange={chooseTheme} />
        <span className="grow" />
        <button type="button" className="btn" onClick={() => window.location.reload()}>
          <Icon name="refresh" />
          Reload screen
        </button>
      </div>

      <h2 className="section-title">Power</h2>
      <PowerButtons />
    </div>
  );
}
