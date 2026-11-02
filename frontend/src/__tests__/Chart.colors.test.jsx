


import React from "react";
import { fireEvent, render, waitFor } from "@testing-library/react";
import Chart from "../components/Chart";

beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = jest.fn(() => ({ measureText: () => ({ width: 60 }) }));
  global.ResizeObserver = class { observe() {} disconnect() {} };
});

test("sensor line patterns match the real Victory legend and remain toggleable", async () => {
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
    fixedDecimals={2} interpolation="linear" isPartitionedBySensor lookback={24}
    topic="od_reading/od1" unitsColorMap={{ unit1: "#0077BB" }} title="OD" yAxisLabel="OD"
  />);
  await waitFor(() => expect(container.querySelector('line[stroke-dasharray="8,4"]')).not.toBeNull());
  for (const dash of ["8,4", "3,3", "8,3,2,3"]) {
    const legend = container.querySelector(`line[stroke-dasharray="${dash}"]`);
    const trace = [...container.querySelectorAll("path")].find((path) => path.style.strokeDasharray === dash);
    expect(trace).toBeDefined();
    expect(trace.style.stroke).toBe(legend.getAttribute("stroke"));
  }
  const legend = container.querySelector('line[stroke-dasharray="8,4"]');
  fireEvent.click(legend);
  await waitFor(() => expect(legend).toHaveAttribute("opacity", "0.4"));
  fireEvent.click(legend);
  await waitFor(() => expect(legend).toHaveAttribute("opacity", "1"));
});
