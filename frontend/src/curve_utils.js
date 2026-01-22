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

export function evaluateCurve(x, curveType, curveData) {
  if (curveType === "spline") {
    return evaluateSpline(x, curveData);
  }
  return evaluatePolynomial(x, curveData);
}

export function generateCurveData(calibration, stepCount = 50) {
  const xValues = calibration?.recorded_data?.x;
  const curveType = calibration?.curve_type || "poly";
  const curveData = calibration?.curve_data_ || [];

  if (!Array.isArray(xValues) || xValues.length === 0) {
    const fallbackXMin = 0;
    const fallbackXMax = 1;
    const stepSize = (fallbackXMax - fallbackXMin) / (stepCount - 1);

    return Array.from({ length: stepCount }).map((_, i) => {
      const x = fallbackXMin + i * stepSize;
      return { x, y: evaluateCurve(x, curveType, curveData) };
    });
  }

  const xMin = Math.min(...xValues);
  const xMax = Math.max(...xValues);

  if (xMin === xMax) {
    return [{ x: xMin, y: evaluateCurve(xMin, curveType, curveData) }];
  }

  const stepSize = (xMax - xMin) / (stepCount - 1);
  const points = [];

  for (let i = 0; i < stepCount; i++) {
    const x = xMin + i * stepSize;
    points.push({ x, y: evaluateCurve(x, curveType, curveData) });
  }
  return points;
}
