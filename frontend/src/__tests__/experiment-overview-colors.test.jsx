import React from "react";
import { render, screen } from "@testing-library/react";
import { colors } from "../utils/color";

jest.mock("../providers/ExperimentContext", () => ({ useExperiment: jest.fn() }));
jest.mock("../providers/MQTTContext", () => ({ useMQTT: jest.fn() }));
jest.mock("../utils/config", () => ({
  getConfig: jest.fn(),
  getRelabelMap: jest.fn((setCallback) => setCallback({})),
}));
jest.mock("../components/LogTable", () => () => null);
jest.mock("../components/ExperimentSummary", () => () => null);
jest.mock("../components/ChartPreferencesControl", () => () => null);
jest.mock("../components/MediaCard", () => () => null);
jest.mock("../Profiles", () => ({ RunningProfilesContainer: () => null }));
jest.mock("../providers/RunningProfilesContext", () => ({
  RunningProfilesProvider: ({ children }) => children,
}));
jest.mock("../components/TimeControls", () => ({
  TimeFormatSwitch: () => null,
  TimeWindowSwitch: () => null,
}));
// The temperature chart renders first and only holds unit3, like a history response that wins the race.
jest.mock("../components/Chart", () => ({ chartKey, unitsColorMap }) => {
  const units = chartKey === "temperature" ? ["unit3"] : ["unit1", "unit2", "unit3"];
  return (
    <div data-testid={`chart-${chartKey}`}>
      {units.map((unit) => `${unit}=${unitsColorMap[unit]}`).join(" ")}
    </div>
  );
});

const { useExperiment } = require("../providers/ExperimentContext");
const { useMQTT } = require("../providers/MQTTContext");
const { getConfig } = require("../utils/config");
const Overview = require("../ExperimentOverview").default;

function mockFetch(workersResponse, overviewUnitColors = {}, historicalUnits = []) {
  global.fetch = jest.fn((url) => {
    if (url === "/api/charts/descriptors") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([
          { chart_key: "optical_density", title: "Optical density" },
          { chart_key: "temperature", title: "Temperature" },
        ]),
      });
    }
    if (url === "/api/experiments/exp1/chart_preferences") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({
          overview_chart_keys: ["temperature", "optical_density"],
          pioreactor_chart_keys: null,
          overview_unit_colors: overviewUnitColors,
        }),
      });
    }
    if (url === "/api/experiments/exp1/historical_worker_assignments") {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(historicalUnits.map((unit) => ({ pioreactor_unit: unit, experiment: "exp1" }))),
      });
    }
    if (url === "/api/experiments/exp1/workers") {
      return Promise.resolve(workersResponse);
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

beforeEach(() => {
  getConfig.mockImplementation((setCallback) => {
    setCallback({ "ui.overview.charts": { optical_density: "1", temperature: "1" } });
    return Promise.resolve();
  });
  useExperiment.mockReturnValue({
    experimentMetadata: { experiment: "exp1", started_at: "2026-03-01T12:00:00Z" },
    updateExperiment: jest.fn(),
  });
  useMQTT.mockReturnValue({ client: null, subscribeToTopic: jest.fn(), unsubscribeFromTopic: jest.fn() });
});

afterEach(() => {
  jest.resetAllMocks();
});

test("unit colors follow the sorted worker list, not which chart loads first", async () => {
  mockFetch({
    ok: true,
    json: () => Promise.resolve(["unit1", "unit2", "unit3"].map((unit) => ({ pioreactor_unit: unit, is_active: 1 }))),
  });
  render(<Overview title="Pioreactor ~ Overview" />);

  expect(await screen.findByTestId("chart-temperature")).toHaveTextContent(`unit3=${colors[2]}`);
  expect(screen.getByTestId("chart-optical_density")).toHaveTextContent(
    `unit1=${colors[0]} unit2=${colors[1]} unit3=${colors[2]}`,
  );
});

test("a chosen color moves only the unit that usually has it", async () => {
  mockFetch(
    {
      ok: true,
      json: () => Promise.resolve(["unit1", "unit2", "unit3"].map((unit) => ({ pioreactor_unit: unit, is_active: 1 }))),
    },
    { unit1: colors[2] },
  );
  render(<Overview title="Pioreactor ~ Overview" />);

  expect(await screen.findByTestId("chart-optical_density")).toHaveTextContent(
    `unit1=${colors[2]} unit2=${colors[1]} unit3=${colors[0]}`,
  );
});

test("previously assigned units take colors after the current ones", async () => {
  mockFetch(
    {
      ok: true,
      json: () => Promise.resolve(["unit1", "unit3"].map((unit) => ({ pioreactor_unit: unit, is_active: 1 }))),
    },
    {},
    ["unit1", "unit2", "unit3"],
  );
  render(<Overview title="Pioreactor ~ Overview" />);

  expect(await screen.findByTestId("chart-optical_density")).toHaveTextContent(
    `unit1=${colors[0]} unit2=${colors[2]} unit3=${colors[1]}`,
  );
});

test("charts still render when the workers request fails", async () => {
  mockFetch({ ok: false, statusText: "Server error" });
  jest.spyOn(console, "error").mockImplementation(() => {});
  render(<Overview title="Pioreactor ~ Overview" />);

  expect(await screen.findByTestId("chart-optical_density")).toBeInTheDocument();
});
