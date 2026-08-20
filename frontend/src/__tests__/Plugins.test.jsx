import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockNavigate = jest.fn();
const mockUseParams = jest.fn();
const mockFetchTaskResult = jest.fn();

jest.mock("react-router", () => {
  const actual = jest.requireActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => mockUseParams(),
  };
});

jest.mock("../utils/tasks", () => ({
  fetchTaskResult: (...args) => mockFetchTaskResult(...args),
  getUnitTaskResult: () => [],
}));

const { MemoryRouter } = require("react-router");
const Plugins = require("../Plugins").default;

function renderPlugins() {
  return render(
    <MemoryRouter>
      <Plugins title="Pioreactor ~ Plugins" />
    </MemoryRouter>,
  );
}

describe("Plugins", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    mockUseParams.mockReturnValue({});
    mockFetchTaskResult.mockResolvedValue({ result: {} });
    global.fetch = jest.fn((url) => {
      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { pioreactor_unit: "unit-1" },
            { pioreactor_unit: "unit-2" },
          ],
        });
      }

      if (url === "/unit_api/usb") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ status: "unmounted" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/list-of-plugins/main/plugins.json") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("selects the plugin target from the page heading", async () => {
    const user = userEvent.setup();
    renderPlugins();

    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toHaveTextContent("Manage plugins for");
    expect(heading.closest("header")).not.toBeNull();

    const targetSelect = await within(heading).findByRole("combobox", {
      name: "Pioreactor",
    });
    await waitFor(() => expect(targetSelect).toBeEnabled());
    expect(within(heading).getByText("unit-1")).toBeVisible();

    await user.click(targetSelect);
    await user.click(screen.getByRole("option", { name: "unit-2" }));

    expect(mockNavigate).toHaveBeenCalledWith("/plugins/unit-2");
    await waitFor(() =>
      expect(mockFetchTaskResult).toHaveBeenCalledWith(
        "/api/units/unit-2/plugins/installed",
      ),
    );

    await user.click(targetSelect);
    await user.click(screen.getByRole("option", { name: /All Pioreactors/ }));

    expect(mockNavigate).toHaveBeenCalledWith("/plugins/$broadcast");
    expect(await screen.findByText("Choose a Pioreactor to view installed plugins.")).toBeVisible();
  });
});
