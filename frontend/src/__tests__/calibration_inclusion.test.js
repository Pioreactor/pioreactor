import { generateCurveData, includedCalibrationPoints } from "../utils/curve_utils";

test("scatter and curve domain omit masked extremes without rounding measurements", () => {
  const calibration = {
    recorded_data: { x: [-100, 0.123456789, 2, 100], y: [-100, 0.123456789, 2, 100] },
    included: [false, true, true, false],
    curve_data_: { type: "poly", coefficients: [1, 0] },
  };
  expect(includedCalibrationPoints(calibration)).toEqual([{ x: 0.123456789, y: 0.123456789 }, { x: 2, y: 2 }]);
  const curve = generateCurveData(calibration);
  expect(curve[0].x).toBe(0.123456789);
  expect(curve.at(-1).x).toBeCloseTo(2);
  delete calibration.included;
  expect(includedCalibrationPoints(calibration)).toHaveLength(4);
});
