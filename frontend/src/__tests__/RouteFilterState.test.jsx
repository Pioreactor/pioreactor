import React from "react";
import { render, screen, within } from "@testing-library/react";
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
        <Route path={`${basePath}/:pioreactorUnit/:device/:name`} element={<h1>Record detail</h1>} />
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

  test.each([
    [Calibrations, "/calibrations", "Calibrations"],
    [Estimators, "/estimators", "Estimators"],
  ])("%s exposes named filters and a record link without duplicate navigation", async (Page, basePath, title) => {
    const user = userEvent.setup();
    renderCollectionPage(Page, basePath, title);
    const link = await screen.findByRole("link", { name: "calibration-unit-1-od" });
    expect(screen.getByRole("combobox", { name: "Pioreactor" })).toHaveTextContent("unit-1");
    expect(screen.getByRole("combobox", { name: "Device" })).toHaveTextContent("od");
    expect(link).toHaveAttribute("href", `${basePath}/unit-1/od/calibration-unit-1-od`);
    await user.click(link);
    expect(screen.getByRole("heading", { name: "Record detail" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByRole("link", { name: "calibration-unit-1-od" })).toBeInTheDocument();
  });

  test.each([
    [Calibrations, "/calibrations", "{Enter}"],
    [Calibrations, "/calibrations", " "],
    [Estimators, "/estimators", "{Enter}"],
    [Estimators, "/estimators", " "],
  ])("%s row navigates with %s %s", async (Page, basePath, key) => {
    const user = userEvent.setup();
    renderCollectionPage(Page, basePath, "Collection");
    const row = (await screen.findByRole("link", { name: "calibration-unit-1-od" })).closest("tr");
    expect(row).toHaveAttribute("tabindex", "0");
    row.focus();
    await user.keyboard(key);
    expect(screen.getByRole("heading", { name: "Record detail" })).toBeInTheDocument();
  });

  test("calibration visibility controls do not open the record", async () => {
    const user = userEvent.setup();
    renderCollectionPage(Calibrations, "/calibrations", "Calibrations");
    const row = (await screen.findByRole("link", { name: "calibration-unit-1-od" })).closest("tr");
    const toggle = within(row).getByRole("button");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    toggle.focus();
    await user.keyboard("{Enter}");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await user.keyboard(" ");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("heading", { name: "Record detail" })).not.toBeInTheDocument();
  });

  test("calibrations follows route history", async () => {
    const user = userEvent.setup();
    renderCollectionPage(Calibrations, "/calibrations", "Calibrations");

    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Go to next route" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(await screen.findByText("calibration-unit-1-od")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Forward" }));
    expect(await screen.findByText("calibration-unit-2-stirring")).toBeInTheDocument();
    expect(fetchTaskResult).toHaveBeenCalledTimes(1);
    expect(fetchTaskResult).toHaveBeenCalledWith(
      "/api/workers/$broadcast/calibrations",
    );
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
    expect(fetchTaskResult).toHaveBeenCalledTimes(1);
    expect(fetchTaskResult).toHaveBeenCalledWith(
      "/api/workers/$broadcast/estimators",
    );
  });
});
