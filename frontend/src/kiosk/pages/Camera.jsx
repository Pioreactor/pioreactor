import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { unitApi, waitForTask } from "../api";
import { cameraPath, captureTime, parseLatestStill, stillUrl } from "../camera";
import { useKiosk } from "../context";
import { useAsync, useTopicStream } from "../hooks";
import { Icon } from "../icons";
import { AsyncButton, Empty, Sheet, useToast } from "../ui";

// The screen shows the culture and takes snapshots. Managing them (automatic
// snapshots, rename, delete, download) is left to the web UI.

// One snapshot, or why there is none. Only this image is decoded: stills are
// full-size JPEGs and there are no thumbnails yet.
function Photo({ experiment, still, emptyText }) {
  const [brokenId, setBrokenId] = useState(null);
  const broken = still && brokenId === still.image_id;

  return (
    <div className="photo-wrap">
      {still && !broken && (
        <img
          key={still.image_id}
          src={stillUrl(experiment, still.image_id)}
          alt={`Camera snapshot ${still.image_id}`}
          decoding="async"
          onError={() => setBrokenId(still.image_id)}
        />
      )}
      {(!still || broken) && (
        <div className="chart-status">{broken ? "This snapshot is no longer available." : emptyText}</div>
      )}
    </div>
  );
}

function emptyTextFor(status) {
  if (status.loading && !status.data) return "Loading...";
  if (status.error && !status.data) return `Could not read the camera status: ${status.error}`;
  const detection = status.data?.detection_status;
  if (detection === "configured_camera_not_detected") return "The configured camera wasn't detected on this Pioreactor.";
  if (detection === "unknown") return "Camera detection didn't finish.";
  return "No snapshots in this experiment yet.";
}

// Props are primitives (plus a stable callback) so memo() skips unchanged rows.
const SnapshotRow = memo(function SnapshotRow({ imageId, label, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`list-row ${selected ? "selected" : ""}`}
      aria-current={selected ? "true" : undefined}
      onClick={() => onSelect(imageId)}
    >
      <span className="grow truncate">{label}</span>
    </button>
  );
});

// Every snapshot in this experiment, newest first: a list of times beside the
// selected photo, so only one image is decoded at a time.
function History({ experiment, onClose }) {
  const list = useAsync((signal) => unitApi(cameraPath(experiment, "stills"), { signal }), [experiment]);
  const [selectedId, setSelectedId] = useState(null);

  const stills = useMemo(() => [...(list.data?.stills || [])].reverse(), [list.data]);
  const index = Math.max(0, stills.findIndex((still) => still.image_id === selectedId));
  const selected = stills[index] || null;
  const select = useCallback((imageId) => setSelectedId(imageId), []);
  // Times are worded once per load, not on every render.
  const labels = useMemo(() => {
    const now = Date.now();
    return new Map(stills.map((still) => [still.image_id, captureTime(still, now)]));
  }, [stills]);

  let body;
  if (list.loading && !list.data) body = <Empty>Loading snapshots...</Empty>;
  else if (list.error && !list.data) body = <Empty>Could not load snapshots: {list.error}</Empty>;
  else if (!stills.length) body = <Empty>No snapshots in this experiment yet.</Empty>;
  else {
    body = (
      <div className="photo-history">
        <div className="list photo-list">
          {stills.map((still) => (
            <SnapshotRow
              key={still.image_id}
              imageId={still.image_id}
              label={labels.get(still.image_id)}
              selected={still === selected}
              onSelect={select}
            />
          ))}
        </div>
        <Photo experiment={experiment} still={selected} />
      </div>
    );
  }

  return (
    <Sheet
      wide
      icon="photos"
      title="Snapshots"
      onClose={onClose}
      footer={
        stills.length > 1 && (
          <>
            <button type="button" className="btn" disabled={index >= stills.length - 1} onClick={() => select(stills[index + 1].image_id)}>
              <Icon name="back" />
              Older
            </button>
            <button type="button" className="btn" disabled={index <= 0} onClick={() => select(stills[index - 1].image_id)}>
              Newer
              <Icon name="forward" />
            </button>
          </>
        )
      }
    >
      {body}
    </Sheet>
  );
}

export default function Camera({ tabs = null }) {
  const { unit, experiment } = useKiosk();
  const toast = useToast();
  const status = useAsync(
    experiment ? (signal) => unitApi(cameraPath(experiment, "status"), { signal }) : null,
    [experiment],
  );
  // From the retained MQTT message: undefined until one arrives, null when the
  // experiment has no snapshots. It wins over the status call's latest_still.
  const [live, setLive] = useState(undefined);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => setLive(undefined), [experiment]);
  useTopicStream([experiment ? `pioreactor/${unit}/${experiment}/camera/latest_still` : null], (_topic, payload) =>
    setLive(parseLatestStill(payload)),
  );

  if (!experiment) return <Empty>Join an experiment to see camera snapshots.</Empty>;

  const still = live !== undefined ? live : status.data?.latest_still ?? null;
  const notDetected = status.data?.detection_status === "configured_camera_not_detected";

  const takeSnapshot = async () => {
    const reply = await unitApi(cameraPath(experiment, "stills"), { method: "POST" });
    const metadata = reply?.result_url_path ? await waitForTask(reply.result_url_path) : reply;
    if (metadata?.image_id) setLive(metadata);
    toast("Snapshot taken.");
  };

  return (
    <div className="content fill">
      <div className="toolbar">
        {tabs}
        <span className="muted grow truncate">{still ? `Taken ${captureTime(still)}` : ""}</span>
        <button type="button" className="btn" onClick={() => setHistoryOpen(true)}>
          <Icon name="photos" />
          History
        </button>
        <AsyncButton className="btn primary" onClick={takeSnapshot} disabled={notDetected} busyLabel="Taking snapshot...">
          <Icon name="camera" />
          Take snapshot
        </AsyncButton>
      </div>
      <Photo experiment={experiment} still={still} emptyText={emptyTextFor(status)} />
      {historyOpen && <History experiment={experiment} onClose={() => setHistoryOpen(false)} />}
    </div>
  );
}
