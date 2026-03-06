import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

const { MemoryRouter } = require("react-router");
const ExperimentSummary = require("../components/ExperimentSummary").default;
const ManageExperimentMenu = require("../components/ManageExperimentMenu").default;
const { useExperiment } = require("../providers/ExperimentContext");

const experiments = [
  {
    experiment: "exp1",
    created_at: "2026-03-01T12:00:00Z",
    description: "Alpha description",
    delta_hours: 10,
    worker_count: 2,
    tags: ["rna", "screening"],
  },
  {
    experiment: "exp2",
    created_at: "2026-03-02T12:00:00Z",
    description: "Beta condition",
    delta_hours: 5,
    worker_count: 0,
    tags: ["archive"],
  },
];

const originalGetBoundingClientRect = HTMLElement.prototype.getBoundingClientRect;

describe("Experiment overview metadata", () => {
  beforeEach(() => {
    HTMLElement.prototype.getBoundingClientRect = () => ({
      width: 120,
      height: 40,
      top: 10,
      left: 10,
      right: 130,
      bottom: 50,
      x: 10,
      y: 10,
      toJSON: () => ({}),
    });

    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            ...experiments[0],
            tags: ["rna", "screening", "scale-up"],
          }),
      }),
    );

    useExperiment.mockReturnValue({
      allExperiments: experiments,
      experimentMetadata: experiments[0],
      updateExperiment: jest.fn(),
      setAllExperiments: jest.fn(),
    });
  });

  afterEach(() => {
    HTMLElement.prototype.getBoundingClientRect = originalGetBoundingClientRect;
    jest.resetAllMocks();
  });

  test("shows experiment tags in the summary", () => {
    render(
      <MemoryRouter>
        <ExperimentSummary experimentMetadata={experiments[0]} updateExperiment={jest.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByText("Tags:")).toBeTruthy();
    expect(screen.getByText("rna")).toBeTruthy();
    expect(screen.getByText("screening")).toBeTruthy();
  });

  test("edits experiment tags from the manage menu", async () => {
    const updateExperiment = jest.fn();
    useExperiment.mockReturnValue({
      allExperiments: experiments,
      experimentMetadata: experiments[0],
      updateExperiment,
      setAllExperiments: jest.fn(),
    });

    render(
      <MemoryRouter>
        <ManageExperimentMenu experiment="exp1" />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /manage experiment/i }));
    fireEvent.click(await screen.findByText("Edit details"));

    const tagsInput = screen.getByLabelText("Tags");
    fireEvent.change(tagsInput, { target: { value: "scale-up" } });
    fireEvent.keyDown(tagsInput, { key: "Enter", code: "Enter", charCode: 13 });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/experiments/exp1",
        expect.objectContaining({
          method: "PATCH",
          body: JSON.stringify({
            description: "Alpha description",
            tags: ["rna", "screening", "scale-up"],
          }),
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
          },
        }),
      ),
    );

    await waitFor(() =>
      expect(updateExperiment).toHaveBeenCalledWith({
        ...experiments[0],
        tags: ["rna", "screening", "scale-up"],
      }),
    );
  });
});
