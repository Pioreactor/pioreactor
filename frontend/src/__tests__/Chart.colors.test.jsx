import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { TextSize } from "victory";
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
  // Legend entries are sorted by label, so 45° (channel 2) comes first.
  const legend = legendSymbols()[0];
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

test("legend labels use the available width and only long ones are shortened", async () => {
  // jsdom can't measure text, so give Victory (and the legend layout) 7px per character.
  const realImpl = TextSize._approximateTextSizeInternal.impl;
  TextSize._approximateTextSizeInternal.impl = (text) => ({ width: String(text).length * 7, height: 15 });
  try {
    const series = Array.from({ length: 6 }, (_, i) => `unit${i + 1}`);
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
      relabelMap={{ unit1: "P3 AirBubbler", unit2: "A very long relabelled bioreactor name 02" }}
      unitsColorMap={Object.fromEntries(series.map((name) => [name, "#0077BB"]))} title="OD" yAxisLabel="OD"
    />);
    const legendLabels = () => [...container.querySelectorAll("text")]
      .filter((node) => /^(P3|A very|unit)/.test(node.textContent));
    await waitFor(() => expect(legendLabels()).toHaveLength(6));

    const texts = legendLabels().map((node) => node.textContent);
    expect(texts).toContain("P3 AirBubbler");
    const shortened = texts.find((text) => text.startsWith("A very"));
    expect(shortened).toMatch(/…02$/);
    expect(shortened.length * 7).toBeLessThanOrEqual(220);

    // 480px of room: the widest packing that fits is 3 per row, so 2 rows.
    const rowYs = new Set(legendLabels().map((node) => node.getAttribute("y")));
    expect(rowYs.size).toBe(2);
  } finally {
    TextSize._approximateTextSizeInternal.impl = realImpl;
  }
});

test("legend entries are in natural order by display label", async () => {
  const series = ["pio10", "Pio3", "pio2", "pio1"];
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
    relabelMap={{ pio1: "zeta" }}
    unitsColorMap={Object.fromEntries(series.map((name) => [name, "#0077BB"]))} title="OD" yAxisLabel="OD"
  />);
  const legendTexts = () => [...container.querySelectorAll("text")]
    .map((node) => node.textContent)
    .filter((text) => /^(pio|Pio|zeta)/.test(text));
  await waitFor(() => expect(legendTexts()).toHaveLength(4));
  expect(legendTexts()).toEqual(["pio2", "Pio3", "pio10", "zeta"]);
});
