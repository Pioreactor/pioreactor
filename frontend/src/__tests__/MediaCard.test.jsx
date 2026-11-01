import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({ client: null, subscribeToTopic: jest.fn(), unsubscribeFromTopic: jest.fn() }),
}));

const { MemoryRouter } = require("react-router");
const MediaCard = require("../components/MediaCard").default;

test("changing start time refreshes per-unit and total rates with a new cache key", async () => {
  const originalStart = "2026-03-01T12:00:00Z";
  const newStart = "2026-03-02T12:00:00Z";
  global.fetch = jest.fn(async url => {
    const mediaRate = new URL(url, "http://localhost").searchParams.get("started_at") === newStart ? 1 : 9;
    return { json: async () => ({ unit1: { mediaRate, altMediaRate: 0 }, all: { mediaRate, altMediaRate: 0 } }) };
  });
  const view = startedAt => <MemoryRouter><MediaCard experiment="exp1" startedAt={startedAt} activeUnits={["unit1", "unit2"]} /></MemoryRouter>;
  const { rerender } = render(view(originalStart));
  await waitFor(() => expect(screen.getAllByText(/9.0mL\/h/)).toHaveLength(2));
  rerender(view(newStart));
  await waitFor(() => expect(screen.getAllByText(/1.0mL\/h/)).toHaveLength(2));
  expect(screen.queryByText(/9.0mL\/h/)).toBeNull();
  expect(global.fetch.mock.calls[0][0]).not.toBe(global.fetch.mock.calls[1][0]);
});
