import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { SnackbarProvider } from "notistack";

import ChartPreferencesControl from "../components/ChartPreferencesControl";


const descriptors = [
  { chart_key: "optical_density", title: "Optical density", source: "app" },
  { chart_key: "temperature", title: "Temperature", source: "app" },
  { chart_key: "volume", title: "Volume", source: "plugin-a" },
];


function renderControl(overrides = {}) {
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
    <SnackbarProvider>
      <ChartPreferencesControl
        chartPageLabel="Overview"
        chartPreferences={chartPreferences}
        experiment="exp1"
      />
    </SnackbarProvider>,
  );

  return { save };
}


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
  expect(within(screen.getByRole("dialog")).getByText("Using chart defaults from the Pioreactor configuration.")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith(null));
});
