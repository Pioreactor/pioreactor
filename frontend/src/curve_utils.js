export function evaluatePolynomial(x, coeffs) {
  if (!coeffs || Array.isArray(coeffs) || !Array.isArray(coeffs.coefficients)) {
    return null;
  }
  const coefficients = coeffs.coefficients;
  if (coefficients.length === 0) {
    return null;
  }
  return coefficients.reduce((acc, coefficient, i) => {
    const power = coefficients.length - 1 - i;
    return acc + coefficient * Math.pow(x, power);
  }, 0);
}

function findIntervalIndex(knots, x) {
  if (!Array.isArray(knots) || knots.length < 2) {
    return 0;
  }
  if (x <= knots[0]) {
    return 0;
  }
  if (x >= knots[knots.length - 1]) {
    return knots.length - 2;
  }
  for (let i = 0; i < knots.length - 1; i++) {
    if (x >= knots[i] && x <= knots[i + 1]) {
      return i;
    }
  }
  return knots.length - 2;
}

export function evaluateSpline(x, splineData) {
  if (!splineData || Array.isArray(splineData)) {
    return null;
  }
  const { knots, coefficients } = splineData;
  if (!Array.isArray(knots) || !Array.isArray(coefficients) || knots.length < 2) {
    return null;
  }
  const index = findIntervalIndex(knots, x);
  const segment = coefficients[index];
  if (!Array.isArray(segment) || segment.length !== 4) {
    return null;
  }
  const [a, b, c, d] = segment;
  const u = x - knots[index];
  return a + b * u + c * u * u + d * u * u * u;
}

export function evaluateAkima(x, akimaData) {
  return evaluateSpline(x, akimaData);
}

export function evaluateCurve(x, curveData) {
  if (!curveData || Array.isArray(curveData)) {
    return null;
  }
  if (curveData.type === "spline") {
    return evaluateSpline(x, curveData);
  }
  if (curveData.type === "akima") {
    return evaluateAkima(x, curveData);
  }
  if (curveData.type === "poly") {
    return evaluatePolynomial(x, curveData);
  }
  return null;
}

export function generateCurveData(calibration, stepCount = 50) {
  const xValues = calibration?.recorded_data?.x;
  const curveData = calibration?.curve_data_;

  if (!Array.isArray(xValues) || xValues.length === 0) {
    const fallbackXMin = 0;
    const fallbackXMax = 1;
    const stepSize = (fallbackXMax - fallbackXMin) / (stepCount - 1);

    return Array.from({ length: stepCount }).map((_, i) => {
      const x = fallbackXMin + i * stepSize;
      return { x, y: evaluateCurve(x, curveData) };
    });
  }

  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);

  if (xMin === xMax) {
    return [{ x: xMin, y: evaluateCurve(xMin, curveData) }];
  }

  const stepSize = (xMax - xMin) / (stepCount - 1);
  const points = [];

  for (let i = 0; i < stepCount; i++) {
    const x = xMin + i * stepSize;
    points.push({ x, y: evaluateCurve(x, curveData) });
  }
  return points;
}
