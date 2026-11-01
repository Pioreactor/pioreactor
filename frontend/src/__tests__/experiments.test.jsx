import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: jest.fn(),
}));

jest.mock("../components/Snackbar", () => ({ open, message }) => open ? <div role="status">{message}</div> : null);

const mockConfirm = jest.fn();
jest.mock("material-ui-confirm", () => ({
  useConfirm: () => mockConfirm,
}));

const { MemoryRouter } = require("react-router");
const Experiments = require("../Experiments").default;
const ManageExperimentMenu = require("../components/ManageExperimentMenu").default;
const { useExperiment } = require("../providers/ExperimentContext");

const experiments = [
  {
    experiment: "exp1",
    created_at: "2026-03-01T12:00:00Z",
    started_at: "2026-03-01T12:00:00Z",
    description: "Alpha description",
    delta_hours: 10,
    worker_count: 2,
    tags: ["rna", "screening"],
  },
  {
    experiment: "exp2",
    created_at: "2026-03-02T12:00:00Z",
    started_at: "2026-03-02T12:00:00Z",
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
    mockConfirm.mockResolvedValue({ confirmed: true, reason: "confirm" });
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(experiments),
      }),
    );
    mockExperimentContext();
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.resetAllMocks();
  });

  test.each([
    ["page", "Delete experiment"],
    ["page", "End experiment"],
    ["menu", "Delete experiment"],
    ["menu", "End experiment"],
  ])("cancelling %s %s sends no mutation", async (view, action) => {
    mockConfirm.mockResolvedValue({ confirmed: false, reason: "cancel" });
    render(<MemoryRouter>{view === "page"
      ? <Experiments title="Experiments" />
      : <ManageExperimentMenu experiment="exp1" />}</MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", {
      name: view === "page" ? "More actions for exp1" : /Manage experiment/,
    }));
    await act(async () => {
      fireEvent.click(screen.getByRole("menuitem", { name: action }));
    });
    expect(mockConfirm).toHaveBeenCalledTimes(1);
    expect(global.fetch.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(false);
    expect(screen.queryByRole("status")).toBeNull();
  });

  test.each(["http", "network", "json"])("preserves remaining experiments when refresh fails: %s", async (failure) => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    let listRequests = 0;
    global.fetch.mockImplementation(async (url, options) => {
      if (options?.method === "DELETE") {
        return { ok: true, json: async () => ({ result_url_path: "/unit_api/task_results/delete" }) };
      }
      if (url === "/unit_api/task_results/delete") {
        return { ok: true, status: 200, json: async () => ({ status: "succeeded", result: {} }) };
      }
      if (++listRequests === 1) return { ok: true, json: async () => experiments };
      if (failure === "network") throw new Error("Offline");
      if (failure === "json") return { ok: true, json: async () => { throw new Error("Invalid JSON"); } };
      return { ok: false, status: 500 };
    });

    render(<MemoryRouter><Experiments title="Experiments" /></MemoryRouter>);
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/experiments", { cache: "no-cache" }));
    fireEvent.click(screen.getByRole("button", { name: "More actions for exp1" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete experiment" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Deleted experiment exp1.");
    expect(screen.getByRole("status")).toHaveTextContent("The experiment list could not be refreshed.");
    expect(screen.getByText("Beta condition")).toBeInTheDocument();
    expect(screen.queryByText("Alpha description")).toBeNull();
    expect(screen.queryByText(/Could not delete/)).toBeNull();
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

  test("editing the start time sends UTC and updates shared metadata", async () => {
    const { updateExperiment } = mockExperimentContext();
    const startedAt = new Date("2026-03-01T15:45:00").toISOString();
    const saved = { ...experiments[0], started_at: startedAt };
    global.fetch.mockImplementation(async (_url, options) => ({
      ok: true,
      json: async () => options?.method === "PATCH" ? saved : experiments,
    }));
    render(<MemoryRouter><Experiments title="Experiments" /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "More actions for exp1" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText(/Experiment start \(local time\)/), {
      target: { value: "2026-03-01T15:45:00" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(updateExperiment).toHaveBeenCalledWith(saved));
    const [, options] = global.fetch.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(JSON.parse(options.body)).toEqual({
      description: experiments[0].description,
      tags: experiments[0].tags,
      started_at: startedAt,
    });
  });

  test("a failed start-time save keeps the draft for retry", async () => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    global.fetch.mockImplementation(async (_url, options) => options?.method === "PATCH"
      ? { ok: false, json: async () => ({ error: "Could not save start time" }) }
      : { ok: true, json: async () => experiments });
    render(<MemoryRouter><Experiments title="Experiments" /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: "More actions for exp1" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit details" }));
    const input = screen.getByLabelText(/Experiment start \(local time\)/);
    fireEvent.change(input, { target: { value: "2026-03-01T15:45" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not save start time");
    expect(input.value).toBe("2026-03-01T15:45");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
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
              started_at: "2026-03-03T12:00:00Z",
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
    expect(global.fetch).toHaveBeenCalledWith("/api/experiments", { cache: "no-cache" });

    expect(await screen.findByText("Gamma condition")).toBeTruthy();
  });
});
