// MQTT payloads are either plain values or JSON structs like
// {"od_filtered": 1.2, "timestamp": "..."}; these helpers read either form.

export function parsePayload(payload) {
  if (payload === undefined || payload === null || payload === "") return null;
  if (payload[0] !== "{" && payload[0] !== "[") return payload;
  try {
    return JSON.parse(payload);
  } catch (_error) {
    return payload;
  }
}

export function readNumber(payload, key) {
  const parsed = parsePayload(payload);
  if (parsed === null) return null;
  const raw = typeof parsed === "object" ? parsed[key] : parsed;
  const number = Number(raw);
  return raw !== null && raw !== "" && Number.isFinite(number) ? number : null;
}

export function readDisplay(payload, key) {
  const parsed = parsePayload(payload);
  if (parsed === null) return null;
  if (typeof parsed !== "object") return String(parsed);
  if (key in parsed && typeof parsed[key] !== "object") return String(parsed[key]);
  return JSON.stringify(parsed);
}

// First photodiode reading in an ODReadings payload: {"ods": {"2": {"od": 0.1, ...}}}.
export function firstOd(payload) {
  const parsed = parsePayload(payload);
  const ods = parsed && typeof parsed === "object" ? parsed.ods : null;
  if (!ods) return null;
  for (const channel of Object.keys(ods).sort()) {
    const od = Number(ods[channel]?.od);
    if (Number.isFinite(od)) return od;
  }
  return null;
}

const JOB_SHORT_NAMES = {
  stirring: "Stir",
  od_reading: "OD",
  growth_rate_calculating: "Growth",
  temperature_automation: "Temp",
  dosing_automation: "Dosing",
  led_automation: "LED",
  add_media: "Add media",
  remove_waste: "Waste",
  add_alt_media: "Alt media",
  experiment_profile: "Profile",
};

export function shortJobName(job) {
  return JOB_SHORT_NAMES[job] || job.replace(/_/g, " ");
}

export const ACTIVE_STATES = new Set(["init", "ready", "sleeping", "lost"]);

// Compact numbers for small screens: 3 significant figures, no exponents for normal ranges.
export function fmt(value, digits = 3) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number)) return null;
  if (number === 0) return "0";
  if (Math.abs(number) >= 10 ** digits) return number.toFixed(0);
  if (Math.abs(number) < 10 ** -digits) return number.toExponential(1);
  return String(Number(number.toPrecision(digits)));
}

export function fmtFixed(value, decimals) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : null;
}
