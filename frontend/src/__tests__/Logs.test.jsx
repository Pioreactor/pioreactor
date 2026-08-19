import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockNavigate = jest.fn();
const mockUseLocation = jest.fn();
const mockUseParams = jest.fn();
const mockUseExperiment = jest.fn();

jest.mock("react-router", () => {
  const actual = jest.requireActual("react-router");
  return {
    ...actual,
    useLocation: () => mockUseLocation(),
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
  };
});

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => mockUseExperiment(),
}));

jest.mock("../components/ManageExperimentMenu", () => () => null);
jest.mock("../components/PaginatedLogsTable", () => () => null);
jest.mock("../utils/config", () => ({
  getRelabelMap: jest.fn(),
}));

const { MemoryRouter } = require("react-router");
const Logs = require("../Logs").default;

function renderLogs() {
  return render(
    <MemoryRouter>
      <Logs title="Pioreactor ~ Logs" />
    </MemoryRouter>,
  );
}

describe("Logs", () => {
  let currentExperimentMetadata;

  beforeEach(() => {
    currentExperimentMetadata = { experiment: "exp-1" };
    mockNavigate.mockReset();
    mockUseLocation.mockReturnValue({ pathname: "/logs" });
    mockUseParams.mockReturnValue({});
    mockUseExperiment.mockImplementation(() => ({
      experimentMetadata: currentExperimentMetadata,
    }));
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: async () => [
          { pioreactor_unit: "unit-1" },
          { pioreactor_unit: "unit-2" },
        ],
      }),
    );
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("records a new event against the current unit and experiment", async () => {
    const user = userEvent.setup();
    const { rerender } = renderLogs();

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    await user.click(screen.getByRole("button", { name: "Record event" }));
    await user.click(within(screen.getByRole("dialog")).getAllByRole("combobox")[0]);
    await user.click(await screen.findByRole("option", { name: "unit-1" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    currentExperimentMetadata = { experiment: "exp-2" };
    mockUseLocation.mockReturnValue({ pathname: "/logs/unit-2" });
    mockUseParams.mockReturnValue({ pioreactorUnit: "unit-2" });
    rerender(
      <MemoryRouter>
        <Logs title="Pioreactor ~ Logs" />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole("button", { name: "Record event" }));
    await user.type(screen.getByRole("textbox", { name: /message/i }), "Fresh event");
    await user.click(screen.getByRole("button", { name: "Record event" }));

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workers/unit-2/experiments/exp-2/logs",
        expect.objectContaining({ method: "POST" }),
      ),
    );
  });
});
