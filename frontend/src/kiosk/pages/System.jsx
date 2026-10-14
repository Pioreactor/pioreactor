import { useState } from "react";
import { unitApi, waitForTask } from "../api";
import { activitiesRunningHere, leaveCluster } from "../cluster";
import { useKiosk } from "../context";
import { useRestartSetup } from "../Onboarding";
import { useAsync, useTopicValues } from "../hooks";
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

const free = (data) => (data ? formatBytes(data.available_bytes) : null);
const total = (data) => (data ? `of ${formatBytes(data.total_bytes)}` : null);

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
    <div className="row-actions">
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

function appVersion(payload) {
  try {
    return JSON.parse(payload)?.app || null;
  } catch (_error) {
    return null;
  }
}

// Updates this unit only (E4 in CLUSTER_MODEL.md). `version` pins a release, to
// match the leader; without it, the latest. The web server restarts during the
// update, so the screen reloads when it's done.
function UpdateButton({ version, label }) {
  const { unit } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();

  const update = async () => {
    const ok = await confirm({
      title: version ? `Update ${unit} to ${version}?` : `Update ${unit}?`,
      message: "This takes a few minutes. Activities will stop; the screen reloads when it's done.",
      confirmText: "Update",
    });
    if (!ok) return;
    const task = await unitApi("/system/update", {
      method: "POST",
      body: { args: [], options: version ? { version } : {}, env: {} },
    });
    toast("Updating... the screen reloads when it's done.");
    try {
      await waitForTask(task.result_url_path, { delayMs: 3000, timeoutMs: 1200000 });
    } catch (_error) {
      // The web server restarts mid-update, which can drop the task; reload anyway.
    }
    window.location.reload();
  };

  return (
    <AsyncButton className="btn" busyLabel="Updating..." onClick={update}>
      <Icon name="refresh" />
      {label}
    </AsyncButton>
  );
}

function LeaveButton() {
  const { unit, leaderHostname, leaderReachable, experiment } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();

  const leave = async () => {
    const running = await activitiesRunningHere();
    if (running.length) {
      toast.error(`Stop ${running.length === 1 ? "this activity" : "these activities"} first: ${running.join(", ")}.`);
      return;
    }
    const ok = await confirm({
      title: `Leave ${leaderHostname}'s cluster?`,
      message: leaderReachable
        ? `${unit} keeps its calibrations and its own config, then restarts. Add it to a cluster again any time.`
        : `Can't reach ${leaderHostname}, so it will still list ${unit}; remove it there later. ${unit} keeps its calibrations and its own config, then restarts.`,
      confirmText: "Leave cluster",
      danger: true,
    });
    if (!ok) return;
    await leaveCluster(unit, { leaderReachable });
    toast(`${unit} is leaving the cluster and restarting...`);
  };

  return (
    <AsyncButton className="btn danger" disabled={Boolean(experiment)} onClick={leave}>
      Leave cluster
    </AsyncButton>
  );
}

function SettingRow({ title, sub, children }) {
  return (
    <div className="list-row">
      <div className="grow">
        <div className="strong">{title}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {children && <div className="row-actions">{children}</div>}
    </div>
  );
}

// Every section is a list of rows: what it is on the left, its controls on the right.
export default function System() {
  const { unit, role, leaderHostname, leaderReachable, isLeader, experiment, config } = useKiosk();
  const [theme, setTheme] = useState(readTheme);
  const restartSetup = useRestartSetup();
  const version = useAsync((signal) => unitApi("/versions/app", { signal }), []);
  const ip = useAsync((signal) => unitApi("/system/ipv4", { signal }), []);
  const disk = useAsync((signal) => unitApi("/system/disk_space", { signal }), [], { refreshMs: 60000 });
  const memory = useAsync((signal) => unitApi("/system/memory", { signal }), [], { refreshMs: 60000 });
  const versionTopic = `pioreactor/${leaderHostname}/$experiment/monitor/versions`;
  const leaderVersion = appVersion(useTopicValues(role === "worker" ? [versionTopic] : [])[versionTopic]);

  const ownVersion = version.data?.version;
  const differs = role === "worker" && leaderVersion && ownVersion && leaderVersion !== ownVersion;
  const leaderAddress = config["cluster.topology"]?.leader_address || leaderHostname;
  // One global UI per cluster, on the leader.
  const uiAddress = isLeader ? ip.data?.ipv4_address || leaderAddress : leaderAddress;

  const chooseTheme = (mode) => {
    applyTheme(mode);
    setTheme(mode);
  };

  return (
    <div className="content">
      <div className="grid-4">
        <ReadValue label="Name" value={unit} />
        <ReadValue label="Address" value={ip.data?.ipv4_address} />
        <ReadValue label="Storage free" value={free(disk.data)} unit={total(disk.data)} />
        <ReadValue label="Memory free" value={free(memory.data)} unit={total(memory.data)} />
      </div>

      <h2 className="section-title">Software</h2>
      <div className="list">
        <SettingRow
          title={ownVersion ? `Version ${ownVersion}` : "Version"}
          sub={differs ? `The leader runs ${leaderVersion}.` : null}
        >
          {differs ? (
            <UpdateButton version={leaderVersion} label={`Update to ${leaderVersion}`} />
          ) : (
            role !== "worker" && <UpdateButton label="Update" />
          )}
        </SettingRow>
      </div>

      <h2 className="section-title">Cluster</h2>
      <div className="list">
        {role === "worker" && (
          <SettingRow
            title={`Leader: ${leaderHostname}${leaderReachable === false ? " (unreachable)" : ""}`}
            sub={experiment ? `To leave the cluster, leave ${experiment} first.` : null}
          >
            <LeaveButton />
          </SettingRow>
        )}
        {uiAddress && (
          <SettingRow
            title="Web interface"
            sub={`Plugins, configuration, exports and the whole cluster: open http://${uiAddress}/ on a computer on this network.`}
          />
        )}
      </div>

      <h2 className="section-title">Screen</h2>
      <div className="list">
        <SettingRow title="Appearance">
          <Segmented label="Appearance" options={THEMES} value={theme} onChange={chooseTheme} />
        </SettingRow>
        <SettingRow title="Setup" sub="Name, Wi-Fi and model.">
          <AsyncButton className="btn" onClick={restartSetup}>
            Run setup again
          </AsyncButton>
        </SettingRow>
        <SettingRow title="Reload screen" sub="If the screen looks stuck.">
          <button type="button" className="btn" onClick={() => window.location.reload()}>
            <Icon name="refresh" />
            Reload
          </button>
        </SettingRow>
      </div>

      <h2 className="section-title">Power</h2>
      <div className="list">
        <SettingRow title="Restart or turn off" sub="Running activities stop.">
          <PowerButtons />
        </SettingRow>
      </div>
    </div>
  );
}
