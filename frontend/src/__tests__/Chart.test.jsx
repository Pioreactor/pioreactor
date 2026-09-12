import React from "react";
import { render, waitFor } from "@testing-library/react";

jest.mock("victory", () => {
  const MockVictoryComponent = ({ children }) => <div>{children}</div>;

  return {
    VictoryAxis: MockVictoryComponent,
    VictoryChart: MockVictoryComponent,
    VictoryGroup: MockVictoryComponent,
    VictoryLabel: MockVictoryComponent,
    VictoryLegend: MockVictoryComponent,
    VictoryLine: MockVictoryComponent,
    VictoryScatter: MockVictoryComponent,
    VictoryTooltip: MockVictoryComponent,
    VictoryVoronoiContainer: MockVictoryComponent,
    VictoryTheme: jest.requireActual("victory").VictoryTheme,
    createContainer: () => MockVictoryComponent,
  };
});

import Chart from "../components/Chart";

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
    measureText: () => ({ width: 10 }),
  }));
  global.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
});

function renderChart(overrides = {}) {
  const subscribeToTopic = jest.fn();
  const unsubscribeFromTopic = jest.fn();
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve({ series: [], data: [] }),
    }),
  );

  const props = {
    allowZoom: false,
    byDuration: false,
    chartKey: "temperature",
    client: {},
    config: {},
    dataSource: "temperature",
    downSample: false,
    experiment: "exp1",
    experimentStartTime: "2026-09-01T00:00:00Z",
    fixedDecimals: 2,
    interpolation: "stepAfter",
    isLiveChart: true,
    lookback: "24h",
    payloadKey: null,
    subscribeToTopic,
    topic: "temperature",
    unsubscribeFromTopic,
    ...overrides,
  };

  return {
    ...render(<Chart {...props} />),
    props,
    subscribeToTopic,
    unsubscribeFromTopic,
  };
}

test("subscribes to the selected unit's chart topic and cleans it up when the unit changes", async () => {
  const { rerender, unmount, props, subscribeToTopic, unsubscribeFromTopic } = renderChart({ unit: "unit1" });

  await waitFor(() => expect(subscribeToTopic).toHaveBeenCalled());
  expect(subscribeToTopic).toHaveBeenCalledWith("pioreactor/unit1/exp1/temperature", expect.any(Function), "Chart");

  rerender(<Chart {...props} unit="unit2" />);

  expect(unsubscribeFromTopic).toHaveBeenCalledWith("pioreactor/unit1/exp1/temperature", "Chart");
  await waitFor(() =>
    expect(subscribeToTopic).toHaveBeenCalledWith("pioreactor/unit2/exp1/temperature", expect.any(Function), "Chart"),
  );

  unmount();
  expect(unsubscribeFromTopic).toHaveBeenCalledWith("pioreactor/unit2/exp1/temperature", "Chart");
});

test("uses the wildcard unit in overview chart topics", async () => {
  const { subscribeToTopic } = renderChart();

  await waitFor(() => expect(subscribeToTopic).toHaveBeenCalled());
  expect(subscribeToTopic).toHaveBeenCalledWith("pioreactor/+/exp1/temperature", expect.any(Function), "Chart");
});
