export async function checkTaskCallback(callbackURL, { maxRetries = 150, delayMs = 100 } = {}) {
  if (maxRetries <= 0) {
    throw new Error("Max retries reached. Stopping.");
  }

  let response;
  try {
    response = await fetch(callbackURL);
  } catch (err) {
    console.error("Error fetching callback:", err);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, { maxRetries: maxRetries - 1, delayMs });
  }

  if (response.status === 202) {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, { maxRetries: maxRetries - 1, delayMs });
  }

  if (!response.ok) {
    throw new Error(`HTTP error! Status: ${response.status}`);
  }

  const payload = await response.json();
  if (payload?.status === "succeeded") {
    return payload;
  }

  if (payload?.status === "failed") {
    throw new Error(payload.error || "Task failed.");
  }

  if (payload?.status === "pending" || payload?.status === "running") {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    return checkTaskCallback(callbackURL, { maxRetries: maxRetries - 1, delayMs });
  }

  throw new Error(`Unexpected task status: ${payload?.status ?? "unknown"}`);
}

export async function fetchTaskResult(
  endpoint,
  { fetchOptions = {}, maxRetries = 100, delayMs = 50 } = {},
) {
  const response = await fetch(endpoint, fetchOptions);
  if (!response.ok) {
    let message = `HTTP error! Status: ${response.status}`;
    try {
      const payload = await response.json();
      if (payload?.error) {
        message = payload.error;
      }
    } catch (_error) {
      // ignore JSON parse errors and fall back to default message
    }
    throw new Error(message);
  }

  const payload = await response.json();
  if (!payload.result_url_path) {
    if (payload?.error) {
      throw new Error(payload.error);
    }
    throw new Error("No result_url_path in response");
  }

  return checkTaskCallback(payload.result_url_path, { maxRetries, delayMs });
}
