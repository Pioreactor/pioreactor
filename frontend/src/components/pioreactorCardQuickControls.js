const AUTOMATION_JOB_KEYS = new Set([
  "temperature_automation",
  "dosing_automation",
  "led_automation",
]);

const QUICK_EDITABLE_TYPES = new Set(["boolean", "numeric", "string"]);

const SPECIAL_CARD_SETTING_DISPLAY_KINDS = {
  "leds.intensity": "led_intensity",
  "pwms.dc": "pwm_dc",
};

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
      { label: "Stop", onClick: onStop, pendingAction: "stop" },
      { label: "Pause", onClick: onPause, pendingAction: "pause" },
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
  return isUnitActive && Boolean(setting?.editable) && supportsQuickEdit && hasValue;
}

export function getCardSettingDisplayKind(jobKey, settingKey) {
  return SPECIAL_CARD_SETTING_DISPLAY_KINDS[`${jobKey}.${settingKey}`] || "default";
}
