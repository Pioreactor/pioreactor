import React from "react";
import { render, waitFor } from "@testing-library/react";

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: jest.fn(),
}));

jest.mock("../utils/config", () => ({
  getConfig: jest.fn((setCallback) =>
    setCallback({
      "ui.overview.cards": {
        dosings: "1",
      },
    }),
  ),
  getRelabelMap: jest.fn((setCallback) => setCallback({})),
}));

jest.mock("../components/LogTable", () => () => null);
jest.mock("../components/ExperimentSummary", () => () => null);
jest.mock("../components/Chart", () => () => null);
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
const { getRelabelMap } = require("../utils/config");
const Overview = require("../ExperimentOverview").default;

describe("ExperimentOverview", () => {
  let contextValue;

  beforeEach(() => {
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
          json: () => Promise.resolve([]),
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
});
