export function unitTargetHeaders(unit) {
  if (!unit) {
    throw new Error("Pioreactor hostname is unavailable. Reload the page and try again.");
  }
  return { "X-Pioreactor-Target": unit };
}
