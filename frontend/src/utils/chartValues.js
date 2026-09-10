// Preserve small sensor signals instead of displaying them as zero.
export function formatChartValue(value, decimals) {
  if (value !== 0 && Math.abs(value) < 10 ** -decimals) {
    return value.toExponential(2);
  }
  return value.toFixed(decimals);
}
