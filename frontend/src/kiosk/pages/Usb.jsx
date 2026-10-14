import { useEffect, useMemo, useRef, useState } from "react";
import { listExperiments } from "../cluster";
import { useKiosk } from "../context";
import { ExperimentList } from "../ExperimentSheet";
import { useAsync } from "../hooks";
import { Icon } from "../icons";
import { AsyncButton, Empty, ExperimentName, Sheet, useConfirm, useToast } from "../ui";
import {
  DEFAULT_DATASETS,
  driveName,
  exportToDrive,
  hasDrive,
  installPlugin,
  installUpdate,
  listArtifacts,
  listDatasets,
  mountDrive,
} from "../usb";

// Plug a drive into this Pioreactor to export data (leaders only: the data
// lives in the leader's database), install plugins, or install an update.

function Row({ title, sub, children }) {
  return (
    <div className="list-row">
      <div className="grow">
        <div className="strong truncate">{title}</div>
        {sub && <div className="sub truncate">{sub}</div>}
      </div>
      {children && <div className="row-actions">{children}</div>}
    </div>
  );
}

/* ---------- Export ---------- */

function DatasetsSheet({ datasets, selected, onChange, onClose }) {
  const toggle = (name) => {
    const next = new Set(selected);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    onChange(next);
  };

  return (
    <Sheet
      title="Datasets"
      onClose={onClose}
      footer={
        <>
          <span className="grow" />
          <button type="button" className="btn primary" onClick={onClose}>
            Done
          </button>
        </>
      }
    >
      <div className="list">
        {datasets.map((dataset) => (
          <button
            type="button"
            key={dataset.dataset_name}
            className={`list-row pick ${selected.has(dataset.dataset_name) ? "on" : ""}`}
            aria-pressed={selected.has(dataset.dataset_name)}
            onClick={() => toggle(dataset.dataset_name)}
          >
            <span className="check">{selected.has(dataset.dataset_name) && <Icon name="check" />}</span>
            <span className="grow">
              <span className="strong truncate">{dataset.display_name}</span>
              {dataset.description && <span className="sub truncate">{dataset.description}</span>}
            </span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

function ExportSection({ writable }) {
  const { experiment: current } = useKiosk();
  const toast = useToast();
  const datasets = useAsync((signal) => listDatasets(signal), []);
  const experiments = useAsync((signal) => listExperiments(signal), []);
  const [experiment, setExperiment] = useState(null);
  const [selected, setSelected] = useState(null);
  const [sheet, setSheet] = useState(null); // "experiment" | "datasets"
  const [saved, setSaved] = useState(null); // the last export's filename

  // This unit's experiment, else the newest one.
  const chosenExperiment = experiment || current || experiments.data?.[0]?.experiment || null;
  const all = useMemo(() => datasets.data || [], [datasets.data]);
  const chosen = useMemo(
    () => selected || new Set(all.map((d) => d.dataset_name).filter((name) => DEFAULT_DATASETS.includes(name))),
    [selected, all],
  );
  const chosenNames = all.filter((d) => chosen.has(d.dataset_name)).map((d) => d.display_name);

  const run = async () => {
    setSaved(null);
    const result = await exportToDrive({ experiment: chosenExperiment, datasets: [...chosen] });
    setSaved(result?.filename || "the export");
    toast(`Saved ${result?.filename || "the export"} to the USB drive.`);
  };

  return (
    <>
      <h2 className="section-title">Export data</h2>
      <div className="list">
        <Row title="Experiment" sub={chosenExperiment ? <ExperimentName name={chosenExperiment} /> : "None yet"}>
          <button type="button" className="btn" onClick={() => setSheet("experiment")}>
            Change...
          </button>
        </Row>
        <Row
          title={`Datasets (${chosen.size})`}
          sub={datasets.data ? chosenNames.join(", ") || "None chosen" : "Loading..."}
        >
          <button type="button" className="btn" disabled={!datasets.data} onClick={() => setSheet("datasets")}>
            Choose...
          </button>
        </Row>
        <Row
          title="Export to the USB drive"
          sub={!writable ? "This drive is read-only." : saved ? `Saved ${saved}. You may now remove the USB.` : ""}
        >
          <AsyncButton
            className="btn primary"
            busyLabel="Exporting..."
            disabled={!writable || !chosenExperiment || chosen.size === 0}
            onClick={run}
          >
            Export
          </AsyncButton>
        </Row>
      </div>

      {sheet === "experiment" && (
        <Sheet title="Experiment to export" icon="experiment" onClose={() => setSheet(null)}>
          <ExperimentList
            exclude={null}
            actionLabel="Choose"
            emptyText="No experiments yet."
            onPick={(name) => {
              setExperiment(name);
              setSheet(null);
            }}
          />
        </Sheet>
      )}
      {sheet === "datasets" && (
        <DatasetsSheet datasets={all} selected={chosen} onChange={setSelected} onClose={() => setSheet(null)} />
      )}
    </>
  );
}

/* ---------- Plugins and updates on the drive ---------- */

function ArtifactSections({ artifacts }) {
  const { role, unit } = useKiosk();
  const confirm = useConfirm();
  const toast = useToast();
  const clusterWide = role === "leader";
  const where = clusterWide ? "every Pioreactor in this cluster" : unit;

  const install = async (plugin) => {
    const name = `${plugin.name}${plugin.version ? ` ${plugin.version}` : ""}`;
    const ok = await confirm({
      title: `Install ${name}?`,
      message: `It's installed on ${where}.`,
      confirmText: "Install",
    });
    if (!ok) return;
    await installPlugin(plugin.path, { clusterWide });
    toast(`Installed ${name}`);
  };

  const update = async (archive) => {
    const ok = await confirm({
      title: `Update to ${archive.version}?`,
      message: `${where[0].toUpperCase()}${where.slice(1)} updates. This takes a few minutes; the screen reloads when it's done.`,
      confirmText: "Update",
    });
    if (!ok) return;
    await installUpdate(archive.path, { clusterWide });
    toast("Updating... the screen reloads when it's done.");
  };

  return (
    <>
      <h2 className="section-title">Plugins</h2>
      <div className="list">
        {artifacts.plugins.length === 0 && <Row title="No plugins on this drive" sub="Plugins are .whl or .py files." />}
        {artifacts.plugins.map((plugin) => (
          <Row key={plugin.path} title={[plugin.name, plugin.version].filter(Boolean).join(" ")}>
            <AsyncButton className="btn" busyLabel="Installing..." onClick={() => install(plugin)}>
              Install
            </AsyncButton>
          </Row>
        ))}
      </div>

      <h2 className="section-title">Software updates</h2>
      <div className="list">
        {artifacts.updates.length === 0 && (
          <Row title="No updates on this drive" sub="Updates are Pioreactor release .zip files." />
        )}
        {artifacts.updates.map((archive) => (
          <Row key={archive.path} title={`Release ${archive.version}`}>
            <AsyncButton className="btn" onClick={() => update(archive)}>
              Update
            </AsyncButton>
          </Row>
        ))}
      </div>
    </>
  );
}

/* ---------- Page ---------- */

export default function Usb() {
  const { usb, isLeader, leaderHostname } = useKiosk();
  const [mountError, setMountError] = useState(null);
  const mounting = useRef(false);
  const present = hasDrive(usb);
  const mounted = usb?.status === "mounted" || usb?.status === "mounted_readonly";
  const name = driveName(usb);
  const artifacts = useAsync(mounted ? (signal) => listArtifacts(signal) : null, [mounted]);

  // Opening the page is the intent to use the drive, so open (mount) it.
  useEffect(() => {
    if (usb?.status !== "present_unmounted" || mounting.current) return;
    mounting.current = true;
    setMountError(null);
    mountDrive()
      .catch((error) => setMountError(error.message))
      .finally(() => {
        mounting.current = false;
      });
  }, [usb?.status]);

  if (!present) {
    return (
      <Empty>
        <Icon name="usb" className="empty-icon" />
        <h1>No USB drive</h1>
        Plug a USB drive into this Pioreactor to export data, install plugins or install an update.
      </Empty>
    );
  }

  let body = null;
  if (usb.status === "unsupported") {
    body = (
      <Empty>
        {usb.partitions?.[0]?.unsupported_reason || "This drive's format isn't supported."} Format it as FAT32 or exFAT
        on a computer.
      </Empty>
    );
  } else if (usb.status === "multiple_present" && !mounted) {
    body = <Empty>More than one USB drive is plugged in. Keep one and remove the others.</Empty>;
  } else if (!mounted) {
    body = <Empty>{mountError ? `Could not open ${name}: ${mountError}` : `Opening ${name}...`}</Empty>;
  } else {
    body = (
      <>
        {isLeader ? (
          <ExportSection writable={usb.status === "mounted"} />
        ) : (
          <>
            <h2 className="section-title">Export data</h2>
            <div className="list">
              <Row
                title="Data is kept on the leader"
                sub={`Plug this drive into ${leaderHostname} and export from its screen.`}
              />
            </div>
          </>
        )}
        {artifacts.error && <div className="banner">Could not read the drive: {artifacts.error}</div>}
        {artifacts.data && <ArtifactSections artifacts={artifacts.data} />}
      </>
    );
  }

  return (
    <div className="content">
      {body}
    </div>
  );
}
