// USB drives plugged into this Pioreactor. Mounting and reading the
// drive are unit-local (/unit_api/usb). Exports come from the leader's database,
// so only the leader's screen exports (to its own drive).
import { useEffect, useRef, useState } from "react";
import { enc, leaderApi, unitApi, waitForTask } from "./api";

// Nothing announces a plugged-in drive yet, so the screen asks. Each check runs
// lsblk on this unit.
const USB_POLL_MS = 4000;

// Datasets ticked by default: what most exports need.
export const DEFAULT_DATASETS = [
  "pioreactor_unit_activity_data",
  "od_readings",
  "od_readings_filtered",
  "growth_rates",
  "temperature_readings",
  "dosing_events",
];

// Status from /unit_api/usb: absent, present_unmounted, mounted, mounted_readonly,
// unsupported, multiple_present or error.
export const hasDrive = (usb) => Boolean(usb && usb.status !== "absent" && usb.status !== "error");

export function driveName(usb) {
  const partition = usb?.active_mount || usb?.partitions?.[0];
  return partition?.display_name || "USB drive";
}

export function useUsbStatus(onInserted) {
  const [usb, setUsb] = useState(null);
  const last = useRef("");
  const onInsertedRef = useRef(onInserted);
  onInsertedRef.current = onInserted;

  useEffect(() => {
    let timer;
    let cancelled = false;
    const check = async () => {
      try {
        const next = await unitApi("/usb");
        const key = JSON.stringify(next);
        if (!cancelled && key !== last.current) {
          const wasPresent = last.current ? hasDrive(JSON.parse(last.current)) : null;
          last.current = key;
          setUsb(next);
          if (wasPresent === false && hasDrive(next)) onInsertedRef.current?.(next);
        }
      } catch (_error) {
        // the web server may be restarting; try again next time
      }
      if (!cancelled) timer = setTimeout(check, USB_POLL_MS);
    };
    check();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  return usb;
}

async function runTask(request) {
  const task = await request;
  return waitForTask(task.result_url_path, { delayMs: 500 });
}

export const mountDrive = () => runTask(unitApi("/usb/mount", { method: "POST" }));
export const listArtifacts = (signal) => unitApi("/usb/artifacts", { signal });

export const listDatasets = (signal) => leaderApi("/datasets/exportable", { signal });

// Writes one zip onto the leader's drive, one file per Pioreactor per dataset.
// Big experiments take minutes.
export async function exportToDrive({ experiment, datasets }) {
  const task = await leaderApi("/datasets/exportable/export-to-usb", {
    method: "POST",
    body: { experiment, datasets, partition_by_unit: true, partition_by_experiment: true },
  });
  return waitForTask(task.result_url_path, { delayMs: 1000, timeoutMs: 1800000 });
}

// The leader of a cluster installs across the cluster; anyone else installs on itself.
export function installPlugin(path, { clusterWide }) {
  const request = clusterWide
    ? leaderApi(`/units/${enc("$broadcast")}/plugins/install-from-leader-usb`, { method: "POST", body: { filepath: path } })
    : unitApi("/plugins/install-from-usb", { method: "POST", body: { filepath: path } });
  return runTask(request);
}

export function installUpdate(path, { clusterWide }) {
  if (clusterWide) {
    return leaderApi("/system/update_from_archive", {
      method: "POST",
      body: { release_archive_location: path, units: "$broadcast" },
    });
  }
  return unitApi("/system/update", { method: "POST", body: { args: [], options: { source: path }, env: {} } });
}
