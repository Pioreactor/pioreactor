export function formatProfileSaveError(payload) {
  if (typeof payload === "string" && payload.trim()) {
    return payload.trim();
  }

  if (!payload || typeof payload !== "object") {
    return "Failed to save profile";
  }

  const messages = [];

  if (typeof payload.error === "string" && payload.error.trim()) {
    messages.push(payload.error.trim());
  }

  if (Array.isArray(payload.diagnostics) && payload.diagnostics.length > 0) {
    const diagnostic =
      payload.diagnostics.find((entry) => entry?.severity === "error") ?? payload.diagnostics[0];
    if (diagnostic && typeof diagnostic.message === "string" && diagnostic.message.trim()) {
      if (typeof diagnostic.path === "string" && diagnostic.path.trim()) {
        messages.push(`${diagnostic.message.trim()} (${diagnostic.path.trim()})`);
      } else {
        messages.push(diagnostic.message.trim());
      }
    }
  }

  if (typeof payload.cause === "string" && payload.cause.trim() && !messages.includes(payload.cause.trim())) {
    messages.push(payload.cause.trim());
  }

  return messages.join(" ") || "Failed to save profile";
}

async function parseErrorPayload(response) {
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    return response.json();
  }

  const text = await response.text();
  return text.trim() || null;
}

export async function saveNewExperimentProfile(code, filename) {
  const response = await fetch("/api/experiment_profiles", {
    method: "POST",
    body: JSON.stringify({ body: code, filename: `${filename}.yaml` }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return;
  }

  const payload = await parseErrorPayload(response);
  throw new Error(formatProfileSaveError(payload));
}

export async function saveExistingExperimentProfile(code, profileFilename) {
  const response = await fetch(`/api/experiment_profiles/${encodeURIComponent(profileFilename)}`, {
    method: "PATCH",
    body: JSON.stringify({ body: code }),
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });

  if (response.ok) {
    return;
  }

  const payload = await parseErrorPayload(response);
  throw new Error(formatProfileSaveError(payload));
}
