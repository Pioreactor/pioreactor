import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ExperimentProvider, useExperiment } from "../providers/ExperimentContext";

const original = {
  experiment: "exp1",
  created_at: "2026-03-01T12:00:00.000Z",
  started_at: "2026-03-01T12:00:00.000Z",
  description: "Original",
  tags: [],
};
const edited = { ...original, started_at: "2026-03-02T12:00:00.000Z" };
const other = { ...original, experiment: "exp2" };

function Consumer() {
  const { experimentMetadata, allExperiments, updateExperiment, selectExperiment } = useExperiment();
  return <>
    <output data-testid="selected">{experimentMetadata.started_at}</output>
    <output data-testid="listed">{allExperiments.find(e => e.experiment === "exp1")?.started_at}</output>
    <button onClick={() => updateExperiment(edited)}>Apply saved metadata</button>
    <button onClick={() => selectExperiment("exp2")}>Select other</button>
    <button onClick={() => selectExperiment("exp1")}>Select edited</button>
  </>;
}

afterEach(() => {
  localStorage.clear();
  jest.restoreAllMocks();
});

test("reload refreshes a recently cached start time from the server", async () => {
  localStorage.setItem("experimentMetadata", JSON.stringify({ ...original, _createdAt: Date.now() }));
  global.fetch = jest.fn(async url => ({
    ok: true,
    json: async () => url === "/api/experiments" ? [edited, other] : edited,
  }));
  render(<ExperimentProvider><Consumer /></ExperimentProvider>);
  await waitFor(() => expect(screen.getByTestId("selected")).toHaveTextContent(edited.started_at));
  expect(screen.getByTestId("listed")).toHaveTextContent(edited.started_at);
  expect(global.fetch).toHaveBeenCalledWith("/api/experiments/exp1", expect.objectContaining({ cache: "no-cache" }));
  expect(JSON.parse(localStorage.getItem("experimentMetadata")).started_at).toBe(edited.started_at);
});

test("saving preserves the new start through experiment switching", async () => {
  localStorage.setItem("experimentMetadata", JSON.stringify(original));
  global.fetch = jest.fn(async url => ({
    ok: true,
    json: async () => url === "/api/experiments" ? [original, other] : original,
  }));
  render(<ExperimentProvider><Consumer /></ExperimentProvider>);
  await waitFor(() => expect(screen.getByTestId("listed")).toHaveTextContent(original.started_at));
  fireEvent.click(screen.getByText("Apply saved metadata"));
  fireEvent.click(screen.getByText("Select other"));
  fireEvent.click(screen.getByText("Select edited"));
  expect(screen.getByTestId("selected")).toHaveTextContent(edited.started_at);
  expect(screen.getByTestId("listed")).toHaveTextContent(edited.started_at);
  expect(JSON.parse(localStorage.getItem("experimentMetadata")).started_at).toBe(edited.started_at);
});
