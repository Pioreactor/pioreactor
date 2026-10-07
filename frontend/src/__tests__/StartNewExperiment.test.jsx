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

  test("keeps character validation and Save availability consistent", () => {
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );

    const nameInput = screen.getByRole("textbox", { name: /Experiment name/ });
    const saveButton = screen.getByRole("button", { name: "Save" });

    for (const character of "#$%+/?\\") {
      fireEvent.change(nameInput, { target: { value: `run${character}1` } });
      expect(nameInput).toHaveAttribute("aria-invalid", "true");
      expect(saveButton).toBeDisabled();
    }

    for (const character of "&=") {
      fireEvent.change(nameInput, { target: { value: `run${character}1` } });
      expect(nameInput).toHaveAttribute("aria-invalid", "false");
      expect(saveButton).toBeEnabled();
    }
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
    const experimentNameInput = screen.getByRole("textbox", { name: /Experiment name/ });
    const descriptionInput = screen.getByRole("textbox", {
      name: "Description (optional - can be edited later)",
    });

    fireEvent.click(populateButton);
    expect(experimentNameInput).toHaveValue("latest-exp");
    expect(descriptionInput).toHaveValue("Latest description");
    expect(screen.getByText("latest-tag")).toBeTruthy();
  });

  test("only considers stored experiment names already used", () => {
    useExperiment.mockReturnValue({
      allExperiments: [...experiments, { experiment: "constructor" }],
      updateExperiment: jest.fn(),
    });
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );
    const input = screen.getByRole("textbox", { name: /Experiment name/ });
    const save = screen.getByRole("button", { name: "Save" });

    for (const name of ["toString", "__proto__", "new-experiment"]) {
      fireEvent.change(input, { target: { value: name } });
      expect(input).toHaveAttribute("aria-invalid", "false");
      expect(save).toBeEnabled();
    }
    for (const name of ["constructor", " latest-exp "]) {
      fireEvent.change(input, { target: { value: name } });
      expect(input).toHaveAttribute("aria-invalid", "true");
      expect(save).toBeDisabled();
    }
  });

  test("allows choosing which previous experiment to populate from", async () => {
    render(
      <MemoryRouter>
        <StartNewExperiment title="Pioreactor ~ Start new experiment" />
      </MemoryRouter>,
    );

    fireEvent.click(await screen.findByRole("button", {name: "Choose a previous experiment"}));
    const menu = await screen.findByRole("menu");
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
