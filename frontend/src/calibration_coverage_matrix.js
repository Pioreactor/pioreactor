import dayjs from "dayjs";

export const COVERAGE_STATUS = {
  ACTIVE: "active",
  AVAILABLE_NOT_ACTIVE: "available_not_active",
  MISSING: "missing",
  UNKNOWN: "unknown",
  NOT_APPLICABLE: "not_applicable",
};

function getLatestCalibration(calibrations = []) {
  if (!Array.isArray(calibrations) || calibrations.length === 0) {
    return null;
  }

  return [...calibrations].sort((a, b) => {
    const aTime = dayjs(a?.created_at).isValid() ? dayjs(a.created_at).valueOf() : 0;
    const bTime = dayjs(b?.created_at).isValid() ? dayjs(b.created_at).valueOf() : 0;
    return bTime - aTime;
  })[0];
}

function isUnknownUnitPayload(unitPayload) {
  if (!unitPayload) return true;
  if (typeof unitPayload !== "object") return true;
  if (Array.isArray(unitPayload)) return true;
  if (unitPayload.error) return true;
  return false;
}

function listDevicesForUnit(unitPayload) {
  if (!unitPayload || typeof unitPayload !== "object" || Array.isArray(unitPayload)) {
    return [];
  }
  return Object.keys(unitPayload);
}

function getUnitKeys(availableByUnit, activeByUnit) {
  return Array.from(
    new Set([
      ...Object.keys(availableByUnit || {}),
      ...Object.keys(activeByUnit || {}),
    ]),
  ).sort();
}

export function deriveCalibrationCoverageMatrix(availableByUnit, activeByUnit) {
  const units = getUnitKeys(availableByUnit, activeByUnit);

  const devices = Array.from(
    new Set(
      units.flatMap((unit) => [
        ...listDevicesForUnit(availableByUnit?.[unit]),
        ...listDevicesForUnit(activeByUnit?.[unit]),
      ]),
    ),
  ).sort();

  const unitHasAnyKnownShape = {};
  units.forEach((unit) => {
    const availableUnit = availableByUnit?.[unit];
    const activeUnit = activeByUnit?.[unit];
    unitHasAnyKnownShape[unit] = !isUnknownUnitPayload(availableUnit) || !isUnknownUnitPayload(activeUnit);
  });

  const cells = {};

  units.forEach((unit) => {
    const availableUnit = availableByUnit?.[unit];
    const activeUnit = activeByUnit?.[unit];
    cells[unit] = {};

    devices.forEach((device) => {
      const availableDeviceValue = !isUnknownUnitPayload(availableUnit) ? availableUnit[device] : undefined;
      const activeDeviceValue = !isUnknownUnitPayload(activeUnit) ? activeUnit[device] : undefined;

      const activeCalibrationName = activeDeviceValue?.calibration_name;
      const hasActive = Boolean(activeCalibrationName);
      const availableList = Array.isArray(availableDeviceValue) ? availableDeviceValue : null;
      const hasAvailable = Array.isArray(availableList) && availableList.length > 0;
      const latestAvailable = getLatestCalibration(availableList || []);

      const knownApplicable = availableList !== null || hasActive;

      if (hasActive) {
        cells[unit][device] = {
          status: COVERAGE_STATUS.ACTIVE,
          calibrationName: activeCalibrationName,
          detailPath: `/calibrations/${unit}/${device}/${activeCalibrationName}`,
          note: "Active calibration is configured for this device.",
        };
        return;
      }

      if (hasAvailable && latestAvailable?.calibration_name) {
        cells[unit][device] = {
          status: COVERAGE_STATUS.AVAILABLE_NOT_ACTIVE,
          calibrationName: null,
          detailPath: `/calibrations/${unit}/${device}`,
          note: "Calibration files exist but none is currently active.",
        };
        return;
      }

      if (availableList !== null && availableList.length === 0) {
        cells[unit][device] = {
          status: COVERAGE_STATUS.MISSING,
          calibrationName: null,
          detailPath: null,
          note: "No calibration files exist for this device.",
        };
        return;
      }

      if (!knownApplicable && unitHasAnyKnownShape[unit]) {
        cells[unit][device] = {
          status: COVERAGE_STATUS.NOT_APPLICABLE,
          calibrationName: null,
          detailPath: null,
          note: "Device appears to be unavailable on this unit.",
        };
        return;
      }

      cells[unit][device] = {
        status: COVERAGE_STATUS.UNKNOWN,
        calibrationName: null,
        detailPath: null,
        note: "",
      };
    });
  });

  return { units, devices, cells };
}
