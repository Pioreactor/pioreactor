import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
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
  let usbStatus;
  let usbArtifacts;

  beforeEach(() => {
    usbStatus = { status: "absent" };
    usbArtifacts = { plugins: [] };
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
          json: async () => usbStatus,
        });
      }

      if (url === "/unit_api/usb/artifacts") {
        return Promise.resolve({ ok: true, json: async () => usbArtifacts });
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

  test("selects the plugin target", async () => {
    const user = userEvent.setup();
    renderPlugins();

    const targetSelect = await screen.findByRole("combobox", { name: "Pioreactor" });
    await waitFor(() => expect(targetSelect).toBeEnabled());
    expect(screen.getByRole("heading", { name: "Installed plugins on unit-1" })).toBeVisible();

    await user.click(targetSelect);
    await user.click(screen.getByRole("option", { name: "unit-2" }));

    expect(mockNavigate).toHaveBeenCalledWith("/plugins/unit-2");
    expect(screen.getByRole("heading", { name: "Installed plugins on unit-2" })).toBeVisible();
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

  test("prompts to attach a USB when none is present", async () => {
    renderPlugins();

    expect(
      await screen.findByText(/You can attach a USB with Pioreactor plugins/),
    ).toBeVisible();
  });

  test("prompts to mount a detected but unmounted USB", async () => {
    usbStatus = { status: "present_unmounted", active_mount: null };
    renderPlugins();

    expect(await screen.findByText(/A USB drive is detected but not mounted/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Leader page" })).toHaveAttribute("href", "/leader");
  });

  test.each(["mounted", "mounted_readonly"])(
    "explains an empty %s USB drive",
    async (status) => {
      usbStatus = {
        status,
        active_mount: { mountpoint: "/media/pioreactor-usb/sda1", display_name: "MyDrive" },
      };
      renderPlugins();

      expect(await screen.findByText(/No plugins found on MyDrive/)).toBeVisible();
      expect(screen.queryByText(/You can attach a USB/)).not.toBeInTheDocument();
    },
  );

  test("lists plugins found on a mounted USB drive", async () => {
    usbStatus = {
      status: "mounted",
      active_mount: { mountpoint: "/media/pioreactor-usb/sda1", display_name: "MyDrive" },
    };
    usbArtifacts = {
      plugins: [
        { name: "my-plugin", version: "1.0.0", kind: "wheel", path: "/media/pioreactor-usb/sda1/my_plugin-1.0.0-py3-none-any.whl" },
      ],
    };
    renderPlugins();

    expect(await screen.findByText("my-plugin")).toBeVisible();
    expect(screen.queryByText(/No plugins found/)).not.toBeInTheDocument();
  });
});
