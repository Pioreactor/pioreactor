import React from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

const { useExperiment } = require("../providers/ExperimentContext");
const StartNewExperiment = require("../StartNewExperiment").default;

const experiments = [
  {
    experiment: "latest-exp",
    created_at: "2026-03-03T12:00:00Z",
    description: "Latest description",
    delta_hours: 1,
    worker_count: 0,
    tags: ["latest-tag"],
  },
  {
    experiment: "second-exp",
    created_at: "2026-03-02T12:00:00Z",
    description: "Second description",
    delta_hours: 2,
    worker_count: 0,
    tags: ["second-tag"],
  },
  {
    experiment: "third-exp",
    created_at: "2026-03-01T12:00:00Z",
    description: null,
    delta_hours: 3,
    worker_count: 0,
    tags: ["third-tag"],
  },
];

describe("Start new experiment", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
    useExperiment.mockReturnValue({
      allExperiments: experiments,
      updateExperiment: jest.fn(),
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("populates fields from the latest experiment", async () => {
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );

    const populateButton = await screen.findByRole("button", {
      name: "Populate from latest-exp",
    });
    expect(within(populateButton).getByTestId("PlayCircleOutlinedIcon")).toBeTruthy();
    expect(within(populateButton).getByText("latest-exp").closest("[data-experiment-name]")).toHaveAttribute(
      "data-experiment-name",
      "latest-exp",
    );
    const experimentNameInput = screen.getByRole("textbox", { name: /Experiment name/ });
    const descriptionInput = screen.getByRole("textbox", {
      name: "Description (optional - can be edited later)",
    });

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("latest-exp");
    expect(descriptionInput).toHaveValue("Latest description");
    expect(screen.getByText("latest-tag")).toBeTruthy();
  });

  test("allows choosing which previous experiment to populate from", async () => {
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", {name: "Choose a previous experiment"}));
    const menu = await screen.findByRole("menu");
    expect(within(menu).queryByText("Search all experiments…")).toBeNull();
    fireEvent.click(within(menu).getByRole("option", {name: /second-exp/}));

    const populateButton = screen.getByRole("button", {name: "Populate from second-exp"});
    fireEvent.click(within(populateButton).getByText("second-exp"));
    const experimentNameInput = screen.getByRole("textbox", { name: /Experiment name/ });
    const descriptionInput = screen.getByRole("textbox", {
      name: "Description (optional - can be edited later)",
    });
    expect(experimentNameInput).toHaveValue("second-exp");
    expect(descriptionInput).toHaveValue("Second description");
    expect(screen.getByText("second-tag")).toBeTruthy();
    expect(global.fetch).not.toHaveBeenCalled();
  });

});
