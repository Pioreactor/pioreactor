import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

jest.mock("notistack", () => ({
  useSnackbar: () => ({
    enqueueSnackbar: jest.fn(),
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

const { MemoryRouter } = require("react-router");
const Experiments = require("../Experiments").default;
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

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("Experiments page", () => {
  beforeEach(() => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(experiments),
      }),
    );

    useExperiment.mockReturnValue({
      allExperiments: experiments,
      experimentMetadata: { experiment: "exp1" },
      selectExperiment: jest.fn(),
      updateExperiment: jest.fn(),
      setAllExperiments: jest.fn(),
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("clicking the experiment chip selects the experiment", async () => {
    const selectExperiment = jest.fn();
    useExperiment.mockReturnValue({
      allExperiments: experiments,
      experimentMetadata: { experiment: "exp1" },
      selectExperiment,
      updateExperiment: jest.fn(),
      setAllExperiments: jest.fn(),
    });

    render(
      <MemoryRouter>
        <Experiments title="Pioreactor ~ Experiments" />
      </MemoryRouter>,
    );

    const chip = await screen.findByText("exp1");
    fireEvent.click(chip);

    expect(selectExperiment).toHaveBeenCalledWith("exp1");
  });

  test("search filters the experiment list", async () => {
    render(
      <MemoryRouter>
        <Experiments title="Pioreactor ~ Experiments" />
      </MemoryRouter>,
    );

    await screen.findByText("Alpha description");

    fireEvent.change(screen.getByLabelText("Search experiments"), {
      target: { value: "beta" },
    });

    await flushPromises();

    expect(screen.queryByText("Alpha description")).toBeNull();
    expect(screen.getByText("Beta condition")).toBeTruthy();
  });
});
