// Display formatting only: never use the result for inputs, storage, or calculations.
export function formatCalibrationNumber(value, precision = 3) {
  if (!Number.isFinite(value)) {
    return "—";
  }
  if (value !== 0 && Math.abs(value) < 10 ** -precision) {
    return value.toExponential(2);
  }
  return Number(value.toFixed(precision)).toString();
}

export function calibrationAxisPrecision(axis) {
  return { rpm: 1, "dc %": 2 }[axis.toLowerCase()] ?? 3;
}
