import {
  evaluatePolynomial,
  evaluateSpline,
  evaluateAkima,
  evaluateCurve,
  generateCurveData,
} from "../curve_utils";

describe("curve_utils", () => {
  test("evaluatePolynomial matches expected value", () => {
    const coeffs = { coefficients: [2, -3, 1] }; // 2x^2 - 3x + 1
    expect(evaluatePolynomial(2, coeffs)).toBeCloseTo(3);
  });

  test("evaluateSpline evaluates segment with local coordinates", () => {
    const splineData = {
      knots: [0, 1, 2],
      coefficients: [
        [0, 1, 0, 0],
        [1, -1, 0, 0],
      ],
    };
    expect(evaluateSpline(0.5, splineData)).toBeCloseTo(0.5);
    expect(evaluateSpline(1.5, splineData)).toBeCloseTo(0.5);
  });

  test("evaluateAkima evaluates segment with local coordinates", () => {
    const akimaData = {
      knots: [0, 1, 2],
      coefficients: [
        [0, 1, 0, 0],
        [1, -1, 0, 0],
      ],
    };
    expect(evaluateAkima(0.5, akimaData)).toBeCloseTo(0.5);
    expect(evaluateAkima(1.5, akimaData)).toBeCloseTo(0.5);
  });

  test("evaluateCurve selects spline or polynomial", () => {
    const splineData = {
      type: "spline",
      knots: [0, 1],
      coefficients: [[1, 1, 0, 0]],
    };
    expect(evaluateCurve(0.25, splineData)).toBeCloseTo(1.25);
    expect(evaluateCurve(0.25, { ...splineData, type: "akima" })).toBeCloseTo(1.25);
    expect(evaluateCurve(2, { type: "poly", coefficients: [1, 0] })).toBeCloseTo(2);
  });

  test("generateCurveData falls back to default domain", () => {
    const calibration = {
      curve_data_: { type: "poly", coefficients: [1, 0] },
      recorded_data: { x: [], y: [] },
    };
    const points = generateCurveData(calibration, 3);
    expect(points).toHaveLength(3);
    expect(points[0]).toEqual({ x: 0, y: 0 });
    expect(points[2]).toEqual({ x: 1, y: 1 });
  });

  test("generateCurveData respects recorded domain", () => {
    const calibration = {
      curve_data_: { type: "poly", coefficients: [1, 0] },
      recorded_data: { x: [2, 4], y: [2, 4] },
    };
    const points = generateCurveData(calibration, 3);
    expect(points[0].x).toBeCloseTo(2);
    expect(points[2].x).toBeCloseTo(4);
  });
});
