import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

const mockExperimentContext = ({
  initialExperiments = experiments,
  experimentMetadata = { experiment: "exp1" },
  selectExperiment = jest.fn(),
  updateExperiment = jest.fn(),
} = {}) => {
  useExperiment.mockImplementation(() => {
    const [allExperiments, setAllExperiments] = React.useState(initialExperiments);

    return {
      allExperiments,
      experimentMetadata,
      selectExperiment,
      updateExperiment,
      setAllExperiments,
    };
  });

  return { selectExperiment, updateExperiment };
};

describe("Experiments page", () => {
  beforeEach(() => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(experiments),
      }),
    );
    mockExperimentContext();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("clicking the experiment chip selects the experiment", async () => {
    const { selectExperiment } = mockExperimentContext();

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

    await waitFor(() => expect(screen.queryByText("Alpha description")).toBeNull());
    expect(screen.getByText("Beta condition")).toBeTruthy();
  });

  test("refresh updates the displayed list through provider state", async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            {
              experiment: "exp3",
              created_at: "2026-03-03T12:00:00Z",
              description: "Gamma condition",
              delta_hours: 1,
              worker_count: 1,
              tags: ["pilot"],
            },
          ]),
      }),
    );

    mockExperimentContext({ initialExperiments: [] });

    render(
      <MemoryRouter>
        <Experiments title="Pioreactor ~ Experiments" />
      </MemoryRouter>,
    );

    expect(screen.queryByText("Gamma condition")).toBeNull();
    expect(global.fetch).toHaveBeenCalledWith("/api/experiments");

    expect(await screen.findByText("Gamma condition")).toBeTruthy();
  });
});
