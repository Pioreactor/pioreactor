import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockNavigate = jest.fn();

jest.mock("react-router", () => {
  const actual = jest.requireActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    selectExperiment: jest.fn(),
  }),
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
const { AssignPioreactors } = require("../Pioreactors");

const assignmentWorkers = [
  {
    pioreactor_unit: "unit-1",
    experiment: null,
  },
  {
    pioreactor_unit: "unit-2",
    experiment: "exp1",
  },
];

function renderAssignPioreactors() {
  return render(
    <MemoryRouter>
      <AssignPioreactors experiment="exp1" />
    </MemoryRouter>,
  );
}

describe("AssignPioreactors", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    global.fetch = jest.fn((url, options = {}) => {
      if (url === "/api/workers/assignments") {
        return Promise.resolve({
          ok: true,
          json: async () => assignmentWorkers,
        });
      }

      if (url === "/api/experiments/exp1/workers" && options.method === "PUT") {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("closes and refreshes after successful assignment changes", async () => {
    renderAssignPioreactors();

    fireEvent.click(screen.getByRole("button", { name: /assign pioreactors/i }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /unit-1/i }));
    fireEvent.click(screen.getByRole("button", { name: "Assign 1" }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(0);
    });
  });

  test("keeps the dialog open and shows an error when assignment update returns non-OK", async () => {
    global.fetch = jest.fn((url, options = {}) => {
      if (url === "/api/workers/assignments") {
        return Promise.resolve({
          ok: true,
          json: async () => assignmentWorkers,
        });
      }

      if (url === "/api/experiments/exp1/workers" && options.method === "PUT") {
        return Promise.resolve({
          ok: false,
          status: 404,
          statusText: "Not Found",
          json: async () => ({ error: "Worker assignment changed." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderAssignPioreactors();

    fireEvent.click(screen.getByRole("button", { name: /assign pioreactors/i }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /unit-1/i }));
    fireEvent.click(screen.getByRole("button", { name: "Assign 1" }));

    expect(
      await screen.findByText("Some Pioreactor assignments could not be updated. Please refresh and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /assign pioreactors/i })).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});
