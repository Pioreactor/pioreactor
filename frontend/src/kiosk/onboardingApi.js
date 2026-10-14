// First-boot setup on a Pioreactor's own screen (KIOSK.md, "Onboarding").
//
// MOCKED until the backend exists. Each mock is named after the endpoint it
// stands in for, waits like a real request, and keeps its state in this screen's
// localStorage (the screen is served by its own unit, so that's per unit for now):
//   - getOnboarding / finishOnboarding / resetOnboarding
//       GET / PUT /unit_api/onboarding {done, completed_at}
//   - renameUnit       POST /unit_api/system/hostname {hostname} -> task; applies after a reboot
//   - getWifiStatus    GET  /unit_api/network/wifi -> {connected, ssid, ethernet, access_point}
//   - scanWifi         GET  /unit_api/network/wifi/scan -> [{ssid, signal, secure}]
//   - connectWifi      POST /unit_api/network/wifi/connect {ssid, password} -> task
//   - listModels (off the leader)   GET /unit_api/models
// Real: getModel / setModel (/unit_api/model), and listModels on the leader (/api/models).
import { leaderApi, unitApi } from "./api";

const STORE_KEY = "pioreactor-kiosk-onboarding-mock";

function readStore() {
  try {
    return JSON.parse(window.localStorage.getItem(STORE_KEY)) || {};
  } catch (_error) {
    return {};
  }
}

function writeStore(patch) {
  const next = { ...readStore(), ...patch };
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(next));
  } catch (_error) {
    // storage may be unavailable; the flow still works for this session
  }
  return next;
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/* ---------- Onboarding state (mock) ---------- */

export async function getOnboarding() {
  await wait(150);
  const { done = false, completed_at: completedAt = null } = readStore();
  return { done, completed_at: completedAt };
}

export async function finishOnboarding() {
  await wait(300);
  writeStore({ done: true, completed_at: new Date().toISOString() });
}

export async function resetOnboarding() {
  await wait(150);
  writeStore({ done: false, completed_at: null });
}

/* ---------- Name (mock) ---------- */

// The new name applies after a reboot, so the screen keeps showing the old one until then.
export async function renameUnit(hostname) {
  await wait(900);
  writeStore({ pending_hostname: hostname });
  return { hostname, applies_after_reboot: true };
}

export const pendingName = () => readStore().pending_hostname || null;

/* ---------- Wi-Fi (mock) ---------- */

const MOCK_NETWORKS = [
  { ssid: "LabNet", signal: 82, secure: true },
  { ssid: "LabNet-Guest", signal: 64, secure: false },
  { ssid: "eduroam", signal: 55, secure: true },
  { ssid: "Building-5G", signal: 31, secure: true },
];

export async function getWifiStatus() {
  await wait(400);
  const { wifi_ssid: ssid = null } = readStore();
  return { connected: Boolean(ssid), ssid, ethernet: false, access_point: false };
}

export async function scanWifi() {
  await wait(1500);
  return MOCK_NETWORKS;
}

// "wrongpassword" fails, so the error path can be tried.
export async function connectWifi(ssid, password) {
  await wait(1200);
  if (password === "wrongpassword") throw new Error(`Incorrect password for ${ssid}.`);
  writeStore({ wifi_ssid: ssid });
  return { connected: true, ssid };
}

/* ---------- Model (real; model list mocked off the leader) ---------- */

export async function getModel() {
  try {
    return await unitApi("/model");
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

export const setModel = (modelName, modelVersion) =>
  unitApi("/model", { method: "PUT", body: { model_name: modelName, model_version: modelVersion } });

export const MOCK_MODELS = [
  { model_name: "pioreactor_40ml", model_version: "1.5", display_name: "Pioreactor 40ml, v1.5" },
  { model_name: "pioreactor_40ml", model_version: "1.0", display_name: "Pioreactor 40ml, v1.0" },
  { model_name: "pioreactor_20ml", model_version: "1.5", display_name: "Pioreactor 20ml, v1.5" },
  { model_name: "pioreactor_20ml", model_version: "1.0", display_name: "Pioreactor 20ml, v1.0" },
];

export async function listModels({ isLeader }) {
  if (!isLeader) {
    await wait(300);
    return MOCK_MODELS;
  }
  const { models } = await leaderApi("/models");
  return models;
}
