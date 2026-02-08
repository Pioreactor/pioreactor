import {
  COVERAGE_STATUS,
  deriveCalibrationCoverageMatrix,
} from "../calibration_coverage_matrix";

describe("deriveCalibrationCoverageMatrix", () => {
  test("maps API payloads into matrix cell statuses", () => {
    const availableByUnit = {
      unitA: {
        od: [
          { calibration_name: "od_old", created_at: "2025-01-01T00:00:00Z" },
          { calibration_name: "od_new", created_at: "2026-01-01T00:00:00Z" },
        ],
        stirring: [],
      },
      unitB: {
        stirring: [
          { calibration_name: "stir_old", created_at: "2025-01-01T00:00:00Z" },
          { calibration_name: "stir_new", created_at: "2026-01-01T00:00:00Z" },
        ],
      },
      unitC: {
        od: [],
      },
      unitD: "broadcast timeout",
    };

    const activeByUnit = {
      unitA: {
        od: { calibration_name: "od_active" },
      },
      unitB: {},
      unitC: {},
    };

    const matrix = deriveCalibrationCoverageMatrix(availableByUnit, activeByUnit);

    expect(matrix.units).toEqual(["unitA", "unitB", "unitC", "unitD"]);
    expect(matrix.devices).toEqual(["od", "stirring"]);

    expect(matrix.cells.unitA.od.status).toEqual(COVERAGE_STATUS.ACTIVE);
    expect(matrix.cells.unitA.od.detailPath).toEqual("/calibrations/unitA/od/od_active");

    expect(matrix.cells.unitB.stirring.status).toEqual(COVERAGE_STATUS.AVAILABLE_NOT_ACTIVE);
    expect(matrix.cells.unitB.stirring.calibrationName).toBeNull();
    expect(matrix.cells.unitB.stirring.detailPath).toEqual("/calibrations/unitB/stirring");

    expect(matrix.cells.unitC.od.status).toEqual(COVERAGE_STATUS.MISSING);

    expect(matrix.cells.unitB.od.status).toEqual(COVERAGE_STATUS.MISSING);

    expect(matrix.cells.unitD.od.status).toEqual(COVERAGE_STATUS.UNKNOWN);
  });
});
