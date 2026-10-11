// HTTP helpers. Unit-local calls go to this Pioreactor's own /unit_api (same
// origin). Cluster-wide data lives on the leader's /api, which accepts
// cross-origin requests from cluster members (see core/pioreactor/web/cors.py).

let leaderOrigin = "";

// "" means the leader is this same origin (the leader's own screen, or the dev proxy).
export function setLeaderOrigin(origin) {
  leaderOrigin = origin;
}

export function leaderUrl(path) {
  return `${leaderOrigin}${path}`;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function errorFromResponse(response) {
  let message = `Error ${response.status}.`;
  try {
    const payload = await response.json();
    if (payload?.error) {
      message = payload.remediation ? `${payload.error} ${payload.remediation}` : payload.error;
    }
  } catch (_error) {
    // keep the status message
  }
  return new ApiError(message, response.status);
}

export async function requestJson(url, { method = "GET", body, signal, headers } = {}) {
  let response;
  try {
    response = await fetch(url, {
      method,
      signal,
      headers: {
        Accept: "application/json",
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the Pioreactor web server.", 0);
  }
  if (!response.ok) throw await errorFromResponse(response);
  if (response.status === 204) return null;
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

export const unitApi = (path, options) => requestJson(`/unit_api${path}`, options);

// Follows a 202 task answer (`result_url_path` on this unit) to its result.
export async function waitForTask(resultUrlPath, { delayMs = 250, timeoutMs = 330000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const task = await requestJson(resultUrlPath);
    if (task?.status === "succeeded") return task.result;
    if (task?.status === "failed") throw new ApiError(task.error || "The task failed.", 200);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
  }
  throw new ApiError("Timed out waiting for this Pioreactor.", 0);
}

export const leaderApi = (path, options) => requestJson(leaderUrl(`/api${path}`), options);

export const enc = encodeURIComponent;
