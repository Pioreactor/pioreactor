import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SnackbarProvider } from "notistack";
import { MemoryRouter } from "react-router";

import ChartPreferencesControl from "../components/ChartPreferencesControl";

jest.mock("../hooks/useLeaderHostname", () => ({
  __esModule: true,
  default: () => "leader",
}));


const descriptors = [
  { chart_key: "optical_density", title: "Optical density", source: "app" },
  { chart_key: "temperature", title: "Temperature", source: "app" },
  { chart_key: "volume", title: "Volume", source: "plugin-a" },
];


function renderControl(overrides = {}, controlProps = {}) {
  const save = jest.fn(() => Promise.resolve());
  const chartPreferences = {
    defaultChartKeys: ["optical_density", "temperature"],
    descriptors,
    error: null,
    isLoading: false,
    isUsingDefaults: false,
    save,
    selectedChartKeys: ["optical_density", "temperature"],
    ...overrides,
  };

  render(
    <MemoryRouter>
      <SnackbarProvider>
        <ChartPreferencesControl
          chartPageLabel="Overview"
          chartPreferences={chartPreferences}
          experiment="exp1"
          {...controlProps}
        />
      </SnackbarProvider>
    </MemoryRouter>,
  );

  return { save };
}


test("opens chart preferences without React warnings", () => {
  const consoleError = jest.spyOn(console, "error");
  const consoleWarn = jest.spyOn(console, "warn");
  try {
    renderControl();
    fireEvent.click(screen.getByRole("button", { name: "Customize Overview charts for this experiment" }));

    expect(screen.getByRole("dialog")).toBeVisible();
    expect(consoleError).not.toHaveBeenCalled();
    expect(consoleWarn).not.toHaveBeenCalled();
  } finally {
    consoleError.mockRestore();
    consoleWarn.mockRestore();
  }
});


test("saves selected charts in the user-defined order", async () => {
  const { save } = renderControl();
  fireEvent.click(screen.getByRole("button", { name: "Customize Overview charts for this experiment" }));

  const temperatureRow = screen.getByText("Temperature").closest("[draggable='true']");
  const opticalDensityRow = screen.getByText("Optical density").closest("[draggable='true']");
  const dataTransfer = {
    dropEffect: "none",
    effectAllowed: "all",
    setData: jest.fn(),
  };
  fireEvent.dragStart(temperatureRow, { dataTransfer });
  fireEvent.dragOver(opticalDensityRow, { dataTransfer });
  fireEvent.drop(opticalDensityRow, { dataTransfer });
  fireEvent.click(screen.getByRole("checkbox", { name: "Volume" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith([
    "temperature",
    "optical_density",
    "volume",
  ]));
});


test("reset restores config inheritance", async () => {
  const { save } = renderControl({
    selectedChartKeys: ["volume"],
  });
  fireEvent.click(screen.getByRole("button", { name: "Customize Overview charts for this experiment" }));

  fireEvent.click(screen.getByRole("button", { name: "Use defaults" }));
  expect(screen.getByRole("checkbox", { name: "Optical density" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Temperature" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Volume" })).not.toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith(null));
});


test("line colors tab saves chosen colors", async () => {
  const { save } = renderControl(
    { unitColors: { unit3: "#CC3311" } },
    { units: ["unit1", "unit2", "unit3"], relabelMap: { unit1: "control" } },
  );
  fireEvent.click(screen.getByRole("button", { name: "Customize Overview charts for this experiment" }));
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual(["Line colors", "Charts"]);
  expect(screen.getByRole("tab", { name: "Line colors" })).toHaveAttribute("aria-selected", "true");
  fireEvent.click(screen.getByRole("button", { name: /^control/ }));

  expect(screen.getByRole("button", { name: "Automatic" })).toHaveAttribute("aria-pressed", "true");
  fireEvent.click(screen.getByRole("button", { name: "#58502F" }));
  // Picking a color closes the row.
  expect(screen.queryByRole("group", { name: "Line color" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^control/ })).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith(
    ["optical_density", "temperature"],
    { unit1: "#58502F", unit3: "#CC3311" },
  ));
});


test("reset all to automatic clears every chosen color", async () => {
  const { save } = renderControl(
    { unitColors: { unit1: "#58502F" } },
    { units: ["unit1"] },
  );
  fireEvent.click(screen.getByRole("button", { name: "Customize Overview charts for this experiment" }));
  fireEvent.click(screen.getByRole("tab", { name: "Line colors" }));
  fireEvent.click(screen.getByRole("button", { name: "Reset all to automatic" }));
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith(["optical_density", "temperature"], {}));
});
