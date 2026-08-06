import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router";

jest.mock("../utils/tasks", () => ({
  ...jest.requireActual("../utils/tasks"),
  fetchTaskResult: jest.fn(),
}));

jest.mock("../components/CalibrationChart", () => () => null);

const { fetchTaskResult } = require("../utils/tasks");
const Calibrations = require("../Calibrations").default;
const Estimators = require("../Estimators").default;

const taskResult = {
  status: "succeeded",
  result: {
    "unit-1": {
      ok: true,
      value: {
        od: [
          {
            calibration_name: "calibration-unit-1-od",
            created_at: "2026-01-01T00:00:00Z",
            estimator_name: "calibration-unit-1-od",
            is_active: true,
            pioreactor_unit: "unit-1",
          },
        ],
        stirring: [
          {
            calibration_name: "calibration-unit-1-stirring",
            created_at: "2026-01-01T00:00:00Z",
            estimator_name: "calibration-unit-1-stirring",
            is_active: true,
            pioreactor_unit: "unit-1",
          },
        ],
      },
    },
    "unit-2": {
      ok: true,
      value: {
        od: [
          {
            calibration_name: "calibration-unit-2-od",
            created_at: "2026-01-02T00:00:00Z",
            estimator_name: "calibration-unit-2-od",
            is_active: true,
            pioreactor_unit: "unit-2",
          },
        ],
        stirring: [
          {
            calibration_name: "calibration-unit-2-stirring",
            created_at: "2026-01-02T00:00:00Z",
            estimator_name: "calibration-unit-2-stirring",
            is_active: true,
            pioreactor_unit: "unit-2",
          },
        ],
      },
    },
  },
};

function RouteHistoryControls({ nextPath }) {
  const navigate = useNavigate();

  return (
    <>
      <button type="button" onClick={() => navigate(nextPath)}>
        Go to next route
      </button>
      <button type="button" onClick={() => navigate(-1)}>
        Back
      </button>
      <button type="button" onClick={() => navigate(1)}>
        Forward
      </button>
    </>
  );
}

function renderCollectionPage(Page, basePath, pageTitle) {
  return render(
    <MemoryRouter initialEntries={[`${basePath}/unit-1/od`]}>
      <RouteHistoryControls nextPath={`${basePath}/unit-2/stirring`} />
      <Routes>
        <Route
          path={`${basePath}/:pioreactorUnit/:device`}
          element={<Page title={pageTitle} />}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("route-backed collection filters", () => {
  beforeEach(() => {
    fetchTaskResult.mockResolvedValue(taskResult);
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => [
        { pioreactor_unit: "unit-1" },
        { pioreactor_unit: "unit-2" },
      ],
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("calibrations follows route history", async () => {
    const user = userEvent.setup();
    renderCollectionPage(Calibrations, "/calibrations", "Calibrations");

    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "calibrations" })).toHaveAttribute(
      "href",
      "https://docs.pioreactor.com/user-guide/managing-calibrations",
    );

    await user.click(screen.getByRole("button", { name: "Go to next route" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Forward" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();
  });

  test("estimators follows route history", async () => {
    const user = userEvent.setup();
    renderCollectionPage(Estimators, "/estimators", "Estimators");

    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to next route" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Forward" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();
  });
});
