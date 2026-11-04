import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react";
import Chart from "../components/Chart";

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({ measureText: () => ({ width: 60 }) }));
  global.ResizeObserver = class { observe() {} disconnect() {} };
});

test.each(["linear", "none"])("sensor legends keep circular swatches and remain toggleable (%s)", async (interpolation) => {
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({
    series: ["unit1-1", "unit1-2", "unit1-3", "unit1-4"],
    data: Array.from({ length: 4 }, () => [
      { x: "2026-09-01T01:00:00Z", y: 1 },
      { x: "2026-09-01T02:00:00Z", y: 2 },
    ]),
  }) });
  const { container } = render(<Chart
    chartKey="od" config={{ "od_config.photodiode_channel": { 1: "90", 2: "45", 3: "135", 4: "180" } }}
    dataSource="od_readings" experiment="exp1" experimentStartTime="2026-09-01T00:00:00Z"
    fixedDecimals={2} interpolation={interpolation} isPartitionedBySensor lookback={24}
    topic="od_reading/od1" unitsColorMap={{ unit1: "#0077BB" }} title="OD" yAxisLabel="OD"
  />);
  const legendSymbols = () => [...container.querySelectorAll("path")].filter((path) => path.style.stroke === "#485157");
  await waitFor(() => expect(legendSymbols()).toHaveLength(4));
  for (const symbol of legendSymbols()) {
    // Victory's circle path uses arcs; triangles, squares, and diamonds do not.
    expect(symbol.getAttribute("d")).toMatch(/a/i);
    expect(symbol.style.fill).toBe("#0077BB");
  }
  const legend = legendSymbols()[1];
  fireEvent.click(legend);
  await waitFor(() => expect(legend.style.fill).toBe("white"));
  fireEvent.click(legend);
  await waitFor(() => expect(legend.style.fill).toBe("#0077BB"));

  if (interpolation === "none") {
    return;
  }
  const traceFor = (dash) => [...container.querySelectorAll("path")].find((path) => path.style.strokeDasharray === dash);
  fireEvent.mouseOver(legend);
  await waitFor(() => expect(traceFor("3,3").style.opacity).toBe("0.2"));
  expect(traceFor("8,4").style.opacity).toBe("1");
  expect(traceFor("8,4").style.strokeWidth).toBe("3");
  fireEvent.mouseOut(legend);
  await waitFor(() => expect(traceFor("3,3").style.opacity).toBe("1"));
});

test("legend labels toggle and dim their series", async () => {
  const series = Array.from({ length: 4 }, (_, i) => `unit${i + 1}`);
  global.fetch = jest.fn().mockResolvedValue({ json: async () => ({
    series,
    data: series.map(() => [
      { x: "2026-09-01T01:00:00Z", y: 1 },
      { x: "2026-09-01T02:00:00Z", y: 2 },
    ]),
  }) });
  const { container } = render(<Chart
    chartKey="od" dataSource="od_readings" experiment="exp1" experimentStartTime="2026-09-01T00:00:00Z"
    fixedDecimals={2} interpolation="linear" lookback={24} topic="od_reading/od1"
    unitsColorMap={Object.fromEntries(series.map((name) => [name, "#0077BB"]))} title="OD" yAxisLabel="OD"
  />);
  const legendLabel = (text) => [...container.querySelectorAll("text")].find((node) => node.textContent === text);
  await waitFor(() => expect(legendLabel("unit4")).toBeTruthy());

  const swatchFor = (index) =>
    [...container.querySelectorAll("path")].filter((path) => path.style.stroke === "#485157")[index];
  fireEvent.click(legendLabel("unit2"));
  await waitFor(() => expect(swatchFor(1).style.fill).toBe("white"));
  expect(legendLabel("unit2").querySelector("tspan").style.opacity).toBe("0.45");
  fireEvent.click(legendLabel("unit2"));
  await waitFor(() => expect(swatchFor(1).style.fill).toBe("#0077BB"));
  expect(legendLabel("unit2").querySelector("tspan").style.opacity).toBe("");
});
