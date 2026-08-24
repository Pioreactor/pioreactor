import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: jest.fn(),
}));

jest.mock("../utils/config", () => ({
  getConfig: jest.fn((setCallback) => {
    setCallback({
      "ui.overview.cards": {
        dosings: "1",
      },
      "ui.overview.charts": {
        optical_density: "1",
        temperature: "1",
      },
    });
    return Promise.resolve();
  }),
  getRelabelMap: jest.fn((setCallback) => setCallback({})),
}));

jest.mock("../components/LogTable", () => () => null);
jest.mock("../components/ExperimentSummary", () => () => null);
jest.mock("../components/Chart", () => ({ chartKey }) => <div data-testid="chart">{chartKey}</div>);
jest.mock("../components/ChartPreferencesControl", () => () => null);
jest.mock("../components/MediaCard", () => () => null);
jest.mock("../Profiles", () => ({
  RunningProfilesContainer: () => null,
}));
jest.mock("../providers/RunningProfilesContext", () => ({
  RunningProfilesProvider: ({ children }) => children,
}));
jest.mock("../components/TimeControls", () => ({
  TimeFormatSwitch: () => null,
  TimeWindowSwitch: () => null,
}));

const { useExperiment } = require("../providers/ExperimentContext");
const { useMQTT } = require("../providers/MQTTContext");
const { getConfig, getRelabelMap } = require("../utils/config");
const Overview = require("../ExperimentOverview").default;

describe("ExperimentOverview", () => {
  let contextValue;

  beforeEach(() => {
    getConfig.mockImplementation((setCallback) => {
      setCallback({
        "ui.overview.cards": { dosings: "1" },
        "ui.overview.charts": {
          optical_density: "1",
          temperature: "1",
        },
      });
      return Promise.resolve();
    });
    contextValue = {
      experimentMetadata: {
        experiment: "exp1",
        description: "Initial description",
        created_at: "2026-03-01T12:00:00Z",
        delta_hours: 10,
      },
      updateExperiment: jest.fn(),
    };

    useExperiment.mockImplementation(() => contextValue);
    useMQTT.mockReturnValue({
      client: null,
      subscribeToTopic: jest.fn(),
      unsubscribeFromTopic: jest.fn(),
    });

    global.fetch = jest.fn((url) => {
      if (url === "/api/charts/descriptors") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([
            {
              chart_key: "optical_density",
              title: "Optical density",
            },
            {
              chart_key: "temperature",
              title: "Temperature",
            },
          ]),
        });
      }

      if (url === "/api/experiments/exp1/chart_preferences") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            overview_chart_keys: ["temperature", "optical_density"],
            pioreactor_chart_keys: null,
          }),
        });
      }

      if (url === "/api/experiments/exp1/workers") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                pioreactor_unit: "unit1",
                is_active: 1,
              },
            ]),
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("does not refetch workers when only the description changes", async () => {
    const { rerender } = render(<Overview title="Pioreactor ~ Overview" />);

    await waitFor(() =>
      expect(
        global.fetch.mock.calls.filter(([url]) => url === "/api/experiments/exp1/workers"),
      ).toHaveLength(1),
    );

    expect(global.fetch).toHaveBeenCalledWith("/api/experiments/exp1/workers");
    expect(getRelabelMap).toHaveBeenCalledTimes(1);

    contextValue = {
      ...contextValue,
      experimentMetadata: {
        ...contextValue.experimentMetadata,
        description: "Updated description",
      },
    };

    rerender(<Overview title="Pioreactor ~ Overview" />);

    await waitFor(() =>
      expect(
        global.fetch.mock.calls.filter(([url]) => url === "/api/experiments/exp1/workers"),
      ).toHaveLength(1),
    );

    const workerFetches = global.fetch.mock.calls.filter(
      ([url]) => url === "/api/experiments/exp1/workers",
    );

    expect(workerFetches).toHaveLength(1);
    expect(getRelabelMap).toHaveBeenCalledTimes(1);
  });

  test("renders charts in the saved experiment order", async () => {
    render(<Overview title="Pioreactor ~ Overview" />);

    await waitFor(() => expect(screen.getAllByTestId("chart")).toHaveLength(2));
    expect(screen.getAllByTestId("chart").map((chart) => chart.textContent)).toEqual([
      "temperature",
      "optical_density",
    ]);
  });
});
