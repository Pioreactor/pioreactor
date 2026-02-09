const AUTOMATION_JOB_KEYS = new Set([
  "temperature_automation",
  "dosing_automation",
  "led_automation",
]);

const QUICK_EDITABLE_TYPES = new Set(["boolean", "numeric", "string"]);
const QUICK_EDIT_DISABLED_LABELS = new Set(["LED intensity", "PWM intensity"]);

export function isAutomationJob(jobKey) {
  return AUTOMATION_JOB_KEYS.has(jobKey);
}

export function shouldClearPendingStateAction(pendingAction, nextState) {
  return (
    (pendingAction === "start" && !["disconnected", "lost", null].includes(nextState)) ||
    (pendingAction === "stop" && nextState === "disconnected") ||
    (pendingAction === "pause" && nextState === "sleeping") ||
    (pendingAction === "resume" && nextState === "ready") ||
    nextState === "lost"
  );
}

export function createStateActionsForState(state, { onPause, onResume, onStop }) {
  if (state === "ready") {
    return [
      { label: "Pause", onClick: onPause, pendingAction: "pause" },
      { label: "Stop", onClick: onStop, pendingAction: "stop" },
    ];
  }

  if (state === "sleeping") {
    return [
      { label: "Resume", onClick: onResume, pendingAction: "resume" },
      { label: "Stop", onClick: onStop, pendingAction: "stop" },
    ];
  }

  return [];
}

export function createPrimaryStateActionForState(state, { onStart, pendingStart }) {
  if (state === "disconnected" || state === "lost") {
    return pendingStart
      ? { onClick: onStart, pendingAction: "start" }
      : { onClick: onStart };
  }

  return null;
}

export function canQuickEditCardSetting(setting, isUnitActive) {
  const value = setting?.value;
  const hasValue = ![null, "", "—", "-"].includes(value);
  const supportsQuickEdit = QUICK_EDITABLE_TYPES.has(setting?.type);
  const isExcludedLabel = QUICK_EDIT_DISABLED_LABELS.has(setting?.label);
  return isUnitActive && Boolean(setting?.editable) && supportsQuickEdit && hasValue && !isExcludedLabel;
}
