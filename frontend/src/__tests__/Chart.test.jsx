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
    jest.advanceTimersByTime(1000);
  });

  const points = getRenderedPoints();
  expect(points.map((point) => point.y)).toEqual([31, 32, 33, 34]);
  expect(points.every((point) => typeof point.x === "number")).toBe(true);
});

test("does not refetch history when the color map identity changes", async () => {
  const { rerender, props } = renderChart({ unit: "unit1", unitsColorMap: { unit1: "#000" } });

  await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  rerender(<Chart {...props} unitsColorMap={{ unit1: "#000" }} />);
  rerender(<Chart {...props} unitsColorMap={{ unit1: "#000" }} />);

  expect(global.fetch).toHaveBeenCalledTimes(1);
});
