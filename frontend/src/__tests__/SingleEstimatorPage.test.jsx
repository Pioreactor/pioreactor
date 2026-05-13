import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockConfirm = jest.fn();

jest.mock("../utils/tasks", () => {
  const actual = jest.requireActual("../utils/tasks");
  return {
    ...actual,
    fetchTaskResult: jest.fn(),
  };
});

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => mockConfirm,
}));

jest.mock("../components/Snackbar", () => ({ open, message }) =>
  open ? <div role="status">{message}</div> : null,
);

jest.mock("../components/DisplaySourceCode", () => ({ sourceCode }) => <pre>{sourceCode}</pre>);

const { MemoryRouter, Route, Routes, useLocation } = require("react-router");
const { fetchTaskResult } = require("../utils/tasks");
const SingleEstimatorPage = require("../SingleEstimatorPage").default;

function estimatorPayload(isActive = false) {
  return {
    result: {
      "unit-1": {
        estimator_type: "od",
        created_at: "2026-05-12T12:00:00Z",
        recorded_data: null,
        is_active: isActive,
        angles: ["90"],
        mu_splines: { 90: { type: "poly", coefficients: [1, 2] } },
        sigma_splines_log: { 90: { type: "poly", coefficients: [1] } },
      },
    },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderSingleEstimatorPage() {
  return render(
    <MemoryRouter initialEntries={["/estimators/unit-1/od90/estimator-a"]}>
      <Routes>
        <Route
          path="/estimators/:pioreactorUnit/:device/:estimatorName"
          element={<SingleEstimatorPage title="Estimator" />}
        />
        <Route path="/estimators/:pioreactorUnit/:device" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SingleEstimatorPage task-backed mutations", () => {
  beforeEach(() => {
    mockConfirm.mockResolvedValue();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/estimators/od90/estimator-a") {
        return Promise.resolve(estimatorPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_estimators/od90/estimator-a") {
        return Promise.resolve({ result: { "unit-1": { status: "success" } } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("waits for the active-estimator task before reporting success", async () => {
    const user = userEvent.setup();
    renderSingleEstimatorPage();

    await screen.findByText("Estimator: estimator-a");
    await user.click(screen.getByRole("button", { name: /set active/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_estimators/od90/estimator-a",
        { fetchOptions: { method: "PATCH" } },
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Estimator set as Active");
  });

  test("shows the unit failure instead of reporting active-estimator success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/estimators/od90/estimator-a") {
        return Promise.resolve(estimatorPayload(false));
      }
      if (endpoint === "/api/workers/unit-1/active_estimators/od90/estimator-a") {
        return Promise.resolve({ result: { "unit-1": null } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleEstimatorPage();

    await screen.findByText("Estimator: estimator-a");
    await user.click(screen.getByRole("button", { name: /set active/i }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Unable to set estimator active on unit-1.",
    );
    expect(screen.queryByText("Estimator set as Active")).not.toBeInTheDocument();
  });

  test("waits for the remove-active task before reporting success", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/estimators/od90/estimator-a") {
        return Promise.resolve(estimatorPayload(true));
      }
      if (endpoint === "/api/workers/unit-1/active_estimators/od90") {
        return Promise.resolve({ result: { "unit-1": { status: "success" } } });
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });

    renderSingleEstimatorPage();

    await screen.findByText("Estimator: estimator-a");
    await user.click(screen.getByRole("button", { name: /set inactive/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/active_estimators/od90",
        { fetchOptions: { method: "DELETE" } },
      ),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Estimator is no longer Active");
  });

  test("waits for the delete task before navigating away", async () => {
    const user = userEvent.setup();
    fetchTaskResult.mockImplementation((endpoint) => {
      if (endpoint === "/api/workers/unit-1/estimators/od90/estimator-a") {
        return Promise.resolve(estimatorPayload(false));
      }
      throw new Error(`Unexpected fetchTaskResult call: ${endpoint}`);
    });
    fetchTaskResult.mockResolvedValueOnce(estimatorPayload(false));
    fetchTaskResult.mockResolvedValueOnce({ result: { "unit-1": { msg: "deleted" } } });

    renderSingleEstimatorPage();

    await screen.findByText("Estimator: estimator-a");
    await user.click(screen.getByRole("button", { name: /delete/i }));

    await waitFor(() =>
      expect(fetchTaskResult).toHaveBeenCalledWith(
        "/api/workers/unit-1/estimators/od90/estimator-a",
        { fetchOptions: { method: "DELETE" } },
      ),
    );
    expect(await screen.findByTestId("location")).toHaveTextContent("/estimators/unit-1/od90");
  });
});
