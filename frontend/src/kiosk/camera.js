import { enc } from "./api";

// Camera snapshots are stored on this Pioreactor and served by its own /unit_api,
// so the Camera tab keeps working while the leader is away.

export const cameraPath = (experiment, suffix) => `/camera/experiments/${enc(experiment)}/${suffix}`;

export const stillUrl = (experiment, imageId) => `/unit_api${cameraPath(experiment, `stills/${enc(imageId)}.jpg`)}`;

// The retained `camera/latest_still` message: a still's metadata, or empty once
// the experiment has no snapshots left.
export function parseLatestStill(payload) {
  if (!payload) return null;
  try {
    const still = JSON.parse(payload);
    return still && typeof still === "object" && still.image_id ? still : null;
  } catch (_error) {
    return null;
  }
}

function parseUtc(timestamp) {
  return Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`);
}

// When a still was taken: the time of day, with the date once it isn't from
// today-ish (as in Logs).
export function captureTime(still, now = Date.now()) {
  const ms = parseUtc(still.captured_at);
  const date = new Date(ms);
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return now - ms > 20 * 3600000 ? `${date.getMonth() + 1}/${date.getDate()} ${time}` : time;
}
