import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
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

  test("repeated populate clicks walk backward through previous experiments", async () => {
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );

    const populateButton = await screen.findByRole("button", {
      name: "Populate from previous experiment",
    });
    const experimentNameInput = screen.getByRole("textbox", { name: /Experiment name/ });
    const descriptionInput = screen.getByRole("textbox", {
      name: "Description (optional - can be edited later)",
    });

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("latest-exp");
    expect(descriptionInput).toHaveValue("Latest description");
    expect(screen.getByText("latest-tag")).toBeTruthy();

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("second-exp");
    expect(descriptionInput).toHaveValue("Second description");
    expect(screen.getByText("second-tag")).toBeTruthy();

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("third-exp");
    expect(descriptionInput).toHaveValue("");
    expect(global.fetch).not.toHaveBeenCalled();
    expect(screen.getByText("third-tag")).toBeTruthy();

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("third-exp");
    expect(descriptionInput).toHaveValue("");
  });

});
