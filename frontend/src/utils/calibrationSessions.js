import { checkTaskCallback } from "./tasks";

// Steps can wait minutes on hardware, so the unit runs each one as a task and
// answers 202. The leader proxies the task's result.
const POLL_DELAY_MS = 250;
const POLL_MAX_RETRIES = 1400; // a bit over the 300 s action timeout

export async function advanceCalibrationSession(unit, sessionId, inputs, fallbackMessage = "Failed to advance session.") {
  const response = await fetch(`/api/workers/${unit}/calibrations/sessions/${sessionId}/inputs`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ inputs }),
  });

  let payload = null;
  try {
    payload = await response.json();
  } catch (_error) {
    // Keep the fallback message.
  }
  if (!response.ok) {
    throw new Error(payload?.error || fallbackMessage);
  }

  const task = await checkTaskCallback(`/api/workers/${unit}/task_results/${payload.task_id}`, {
    maxRetries: POLL_MAX_RETRIES,
    delayMs: POLL_DELAY_MS,
  });
  return task.result;
}

export function isDataReviewStep(step) {
  return Array.isArray(step?.fields) && step.fields.some((field) => field.field_type === "data_table");
}

// Inputs that accept a review step's data tables exactly as recorded.
export function recordedDataInputs(step) {
  const inputs = {};
  (step?.fields || []).forEach((field) => {
    if (field.field_type === "data_table") {
      inputs[field.name] = field.default || [];
    }
  });
  return inputs;
}
