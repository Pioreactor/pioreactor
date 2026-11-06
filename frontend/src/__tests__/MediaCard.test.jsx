import React from "react";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: jest.fn(),
}));

const { useMQTT } = require("../providers/MQTTContext");
const { MemoryRouter } = require("react-router");
const MediaCard = require("../components/MediaCard").default;

beforeEach(() => {
  useMQTT.mockReturnValue({ client: null, subscribeToTopic: jest.fn(), unsubscribeFromTopic: jest.fn() });
});

test("changing start time refreshes per-unit and total rates with a new cache key", async () => {
  const originalStart = "2026-03-01T12:00:00Z";
  const newStart = "2026-03-02T12:00:00Z";
  global.fetch = jest.fn(async url => {
    if (url.endsWith("/historical_worker_assignments")) {
      return { ok: true, json: async () => [{ pioreactor_unit: "unit1" }, { pioreactor_unit: "unit2" }] };
    }
    const mediaRate = new URL(url, "http://localhost").searchParams.get("started_at") === newStart ? 1 : 9;
    return { json: async () => ({ unit1: { mediaRate, altMediaRate: 0 }, all: { mediaRate, altMediaRate: 0 } }) };
  });
  const view = startedAt => <MemoryRouter><MediaCard experiment="exp1" startedAt={startedAt} /></MemoryRouter>;
  const { rerender } = render(view(originalStart));
  await waitFor(() => expect(screen.getAllByText(/9.0mL\/h/)).toHaveLength(2));
  rerender(view(newStart));
  await waitFor(() => expect(screen.getAllByText(/1.0mL\/h/)).toHaveLength(2));
  expect(screen.queryByText(/9.0mL\/h/)).toBeNull();
  const rateUrls = global.fetch.mock.calls.map(([url]) => url).filter(url => url.includes("/media_rates?"));
  expect(rateUrls).toHaveLength(2);
  expect(rateUrls[0]).not.toBe(rateUrls[1]);
});

test("includes previously assigned Pioreactors and their dosing totals in natural order", async () => {
  const subscribeToTopic = jest.fn();
  useMQTT.mockReturnValue({ client: {}, subscribeToTopic, unsubscribeFromTopic: jest.fn() });
  global.fetch = jest.fn(async url => ({
    ok: true,
    json: async () => url.endsWith("/historical_worker_assignments") ? [
      { pioreactor_unit: "unit10", is_currently_assigned_to_experiment: 0 },
      { pioreactor_unit: "unit2", is_currently_assigned_to_experiment: 1 },
    ] : {
      unit10: { mediaRate: 3, altMediaRate: 1 },
      all: { mediaRate: 3, altMediaRate: 1 },
    },
  }));
  render(<MemoryRouter><MediaCard experiment="exp1" startedAt="2026-03-01T12:00:00Z" relabelMap={{ unit10: "Former culture" }} /></MemoryRouter>);

  await screen.findByRole("link", { name: "Former culture / unit10" });
  const onMessage = subscribeToTopic.mock.calls[0][1];
  act(() => {
    onMessage("pioreactor/unit10/exp1/bioreactor/cumulative_media_added_ml", JSON.stringify({ value: 12.5 }));
    onMessage("pioreactor/unit10/exp1/bioreactor/cumulative_alt_media_added_ml", JSON.stringify({ value: 4.5 }));
  });

  const rows = within(screen.getByRole("table")).getAllByRole("row");
  expect(rows[1]).toHaveTextContent("unit2");
  expect(rows[2]).toHaveTextContent("Former culture / unit10");
  expect(within(rows[2]).getByText("12.5mL (3.0mL/h)")).toBeInTheDocument();
  expect(within(rows[2]).getByText("4.5mL (1.0mL/h)")).toBeInTheDocument();
  expect(rows[3]).toHaveTextContent("All historically assigned Pioreactors");
  expect(within(rows[3]).getByText("12.5mL (3.0mL/h)")).toBeInTheDocument();
});
