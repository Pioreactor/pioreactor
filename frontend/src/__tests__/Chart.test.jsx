import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import dayjs from "dayjs";
import utc from "dayjs/plugin/utc";

dayjs.extend(utc);

jest.mock("victory", () => {
  const MockVictoryComponent = ({ children }) => <div>{children}</div>;
  const MockVictoryGroup = ({ children, data }) => (
    <div data-testid="series" data-points={JSON.stringify(data)}>{children}</div>
  );

  return {
    VictoryAxis: MockVictoryComponent,
    VictoryChart: MockVictoryComponent,
    VictoryGroup: MockVictoryGroup,
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

import Chart, { thinSeriesData } from "../components/Chart";

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({
    measureText: () => ({ width: 10 }),
  }));
  global.ResizeObserver = class {
    observe() {}
    disconnect() {}
  };
});

afterEach(() => {
  jest.useRealTimers();
});

function renderChart(overrides = {}, historicalData = { series: [], data: [] }) {
  const subscribeToTopic = jest.fn();
  const unsubscribeFromTopic = jest.fn();
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve(historicalData),
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

const formatServerTimestamp = (ms) => dayjs.utc(ms).format("YYYY-MM-DDTHH:mm:ss.SSS");

function getRenderedPoints() {
  return JSON.parse(screen.getByTestId("series").getAttribute("data-points"));
}

test("batches live points into one update and drops points older than the lookback window", async () => {
  const now = Date.now();
  const { subscribeToTopic } = renderChart(
    { lookback: 1, payloadKey: "temperature" },
    {
      series: ["unit1"],
      data: [[
        { x: formatServerTimestamp(now - 2 * 60 * 60 * 1000), y: 30 },
        { x: formatServerTimestamp(now - 10 * 60 * 1000), y: 31 },
      ]],
    },
  );

  await waitFor(() => expect(getRenderedPoints()).toHaveLength(2));
  const onMessage = subscribeToTopic.mock.calls.at(-1)[1];

  jest.useFakeTimers();
  act(() => {
    for (const y of [32, 33, 34]) {
      onMessage(
        "pioreactor/unit1/exp1/temperature_automation/temperature",
        JSON.stringify({ timestamp: new Date(now).toISOString(), temperature: y }),
        { retain: false },
      );
    }
  });
  expect(getRenderedPoints()).toHaveLength(2);

  act(() => {
    jest.advanceTimersByTime(5000);
  });

  const points = getRenderedPoints();
  expect(points.map((point) => point.y)).toEqual([31, 32, 33, 34]);
  expect(points.every((point) => typeof point.x === "number")).toBe(true);
});

test("keeps every live point when the lookback is 0", async () => {
  const now = Date.now();
  const { subscribeToTopic } = renderChart({ lookback: 0, payloadKey: "temperature" });

  await waitFor(() => expect(global.fetch).toHaveBeenCalled());
  // Let the (empty) history fetch resolve so live messages are accepted.
  await act(async () => {});
  const onMessage = subscribeToTopic.mock.calls.at(-1)[1];

  jest.useFakeTimers();
  act(() => {
    for (const [offsetMs, y] of [[-60 * 1000, 32], [-1000, 33]]) {
      onMessage(
        "pioreactor/unit1/exp1/temperature_automation/temperature",
        JSON.stringify({ timestamp: new Date(now + offsetMs).toISOString(), temperature: y }),
        { retain: false },
      );
    }
  });

  act(() => {
    jest.advanceTimersByTime(5000);
  });

  expect(getRenderedPoints().map((point) => point.y)).toEqual([32, 33]);
});

test("does not refetch history when the color map identity changes", async () => {
  const { rerender, props } = renderChart({ unit: "unit1", unitsColorMap: { unit1: "#000" } });

  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  rerender(<Chart {...props} unitsColorMap={{ unit1: "#000" }} />);
  rerender(<Chart {...props} unitsColorMap={{ unit1: "#000" }} />);

  expect(global.fetch).toHaveBeenCalledTimes(1);
});

test("repeated thinning keeps coverage of history while live points keep arriving", () => {
  const maxPoints = 2800;
  const targetPoints = maxPoints / 2;
  // Server history: 1,400 evenly sampled points, then live points one at a time, flushed in batches.
  let data = Array.from({ length: 1400 }, (_, x) => ({ x, y: x }));
  for (let batchStart = 1400; batchStart < 30000; batchStart += 10) {
    const batch = Array.from({ length: 10 }, (_, offset) => ({ x: batchStart + offset, y: batchStart + offset }));
    data = thinSeriesData(data.concat(batch), maxPoints);
    expect(data.length).toBeLessThanOrEqual(maxPoints);
  }

  const xs = data.map((point) => point.x);
  expect(xs[0]).toBe(0);
  expect(xs.at(-1)).toBe(29999);
  expect(xs.every((x, i) => i === 0 || x > xs[i - 1])).toBe(true);

  // History covers ~4.7% of the span, so it should keep roughly that share of the grid, not one point.
  expect(xs.filter((x) => x < 1400).length).toBeGreaterThanOrEqual(60);

  // No stretch of the interval, old or new, is left much sparser than the grid spacing.
  const gridSpacing = 29999 / (targetPoints - 1);
  const maxGap = Math.max(...xs.slice(1).map((x, i) => x - xs[i]));
  expect(maxGap).toBeLessThanOrEqual(2 * gridSpacing);
});

test("thinning leaves series within budget untouched", () => {
  const data = [{ x: 0, y: 1 }, { x: 1, y: 2 }];
  expect(thinSeriesData(data, 2)).toBe(data);
  expect(thinSeriesData(data, Infinity)).toBe(data);
});
