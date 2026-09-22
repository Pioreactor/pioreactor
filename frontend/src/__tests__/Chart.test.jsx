import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";

jest.mock("victory", () => {
  const MockVictoryComponent = ({ children }) => <div>{children}</div>;

  return {
    VictoryAxis: ({ dependentAxis, domain }) => dependentAxis ? <div data-testid="y-domain">{JSON.stringify(domain)}</div> : null,
    VictoryChart: MockVictoryComponent,
    VictoryGroup: ({ children, data }) => <div data-testid="series-data">{JSON.stringify(data)}{children}</div>,
    VictoryLabel: MockVictoryComponent,
    VictoryLegend: MockVictoryComponent,
    VictoryLine: MockVictoryComponent,
    VictoryScatter: ({ name }) => <div>{name}</div>,
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

function renderChart(overrides = {}, history = { series: [], data: [] }) {
  const subscribeToTopic = jest.fn();
  const unsubscribeFromTopic = jest.fn();
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve(history),
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

test("keeps small reflectance values visible instead of rounding to zero", () => {
  const { formatChartValue } = require("../utils/chartValues.js");
  expect(formatChartValue(7.45279e-7, 3)).toBe("7.45e-7");
  expect(formatChartValue(0.125, 3)).toBe("0.125");
});

test.each([false, true].flatMap((historical) => [0, 45, 90, 135, 180].map((angle) => [historical, angle])))
("uses recorded geometry despite REF config (history=%s, angle=%s)", async (historical, angle) => {
  const history = historical ? {
    series: ["unit1-1"],
    data: [[{ x: "2026-09-01T01:00:00Z", y: 7.45279e-7, angle }]],
  } : { series: [], data: [] };
  const { subscribeToTopic } = renderChart({
    chartKey: "optical_density", dataSource: "od_readings", topic: "od_reading/od1",
    payloadKey: "od", isPartitionedBySensor: true,
    config: { "od_config.photodiode_channel": { "1": "REF" } },
    yAxisDomain: [0.001, 0.05],
  }, history);
  await waitFor(() => expect(subscribeToTopic.mock.calls.length).toBeGreaterThan(1));
  if (!historical) {
    const callback = subscribeToTopic.mock.calls.at(-1)[1];
    act(() => callback("pioreactor/unit1/exp1/od_reading/od1", JSON.stringify({
      calibrated: 0, od: 7.45279e-7, angle: String(angle), timestamp: "2026-09-01T01:00:00Z",
    }), { retain: false }));
  }
  await waitFor(() => expect(screen.getByTestId("series-data").textContent).toContain("7.45279e-7"));
  expect(screen.getByTestId("y-domain").textContent).toBe("null");
  expect(screen.getByText(`unit1-${angle}°`)).toBeTruthy();
});


test("keeps historical geometry changes and mixed units separate", async () => {
  renderChart({
    chartKey: "optical_density", dataSource: "od_readings", topic: "od_reading/od1",
    payloadKey: "od", isPartitionedBySensor: true,
  }, {
    series: ["unit1-1", "unit2-1"],
    data: [
      [{ x: "2026-09-01T01:00:00Z", y: 0.1, angle: 45 },
       { x: "2026-09-01T02:00:00Z", y: 0.2, angle: 135 }],
      [{ x: "2026-09-01T01:00:00Z", y: 7e-7, angle: 0 }],
    ],
  });
  await waitFor(() => expect(screen.getAllByTestId("series-data")).toHaveLength(3));
  for (const name of ["unit1-45°", "unit1-135°", "unit2-0°"]) {
    expect(screen.getByText(name)).toBeTruthy();
  }
});

test("labels unmatched raw history by channel without guessing geometry", async () => {
  renderChart({
    chartKey: "raw_optical_density", dataSource: "raw_od_readings", topic: "od_reading/raw_od1",
    payloadKey: "od", isPartitionedBySensor: true, unit: "unit1",
    config: { "od_config.photodiode_channel": { "1": "90" } },
  }, {
    series: ["unit1-1"],
    data: [[{ x: "2026-09-01T01:00:00Z", y: 0.1, angle: null }]],
  });
  await waitFor(() => expect(screen.getByText("unit1-channel 1")).toBeTruthy());
});
