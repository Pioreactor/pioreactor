import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SnackbarProvider } from "notistack";

import AutomationForm from "../components/AutomationForm";
import DosingAutomationForm from "../components/DosingAutomationForm";
import ChangeAutomationsDialog from "../components/ChangeAutomationsDialog";
import ChangeDosingAutomationsDialog from "../components/ChangeDosingAutomationsDialog";

const mockRunPioreactorJob = jest.fn();

jest.mock("../utils/jobs", () => ({
  runPioreactorJob: (...args) => mockRunPioreactorJob(...args),
}));

const renderWithSnackbar = (ui) => render(<SnackbarProvider>{ui}</SnackbarProvider>);

describe("automation forms", () => {
  beforeEach(() => {
    mockRunPioreactorJob.mockReset();
    global.fetch = jest.fn((url) => {
      if (url === "/api/automations/descriptors/temperature") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                automation_name: "thermostat",
                display_name: "Thermostat",
                description: "Keep temperature steady.",
                fields: [
                  { key: "target_temperature", label: "Target temperature", type: "numeric", default: 37, unit: "C" },
                  { key: "mode", label: "Mode", type: "select", default: "normal", options: ["normal", "aggressive"] },
                ],
              },
            ]),
        });
      }

      if (url === "/api/automations/descriptors/dosing") {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                automation_name: "chemostat",
                display_name: "Chemostat",
                description: "Maintain a fixed dilution rate.",
                fields: [
                  { key: "duration", label: "Duration", type: "numeric", default: 30, unit: "min" },
                  { key: "exchange_volume_ml", label: "Exchange volume", type: "numeric", default: 1.5, unit: "ml" },
                ],
              },
            ]),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("AutomationForm only reports user-driven changes", () => {
    const updateParent = jest.fn();

    render(
      <AutomationForm
        fields={[
          { key: "target_temperature", label: "Target temperature", type: "numeric", default: 37, unit: "C" },
        ]}
        description="Keep temperature steady."
        updateParent={updateParent}
        name="thermostat"
        settings={{ target_temperature: 37 }}
      />,
    );

    expect(updateParent).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Target temperature"), {
      target: { id: "target_temperature", value: "39", valueAsNumber: 39 },
    });

    expect(updateParent).toHaveBeenCalledWith({ target_temperature: 39 });
  });

  test("AutomationForm keeps cleared numeric inputs empty instead of restoring defaults", () => {
    function Harness() {
      const [settings, setSettings] = React.useState({ target_temperature: 37 });

      return (
        <AutomationForm
          fields={[
            { key: "target_temperature", label: "Target temperature", type: "numeric", default: 37, unit: "C" },
          ]}
          description="Keep temperature steady."
          updateParent={(partial) => setSettings((previous) => ({ ...previous, ...partial }))}
          name="thermostat"
          settings={settings}
        />
      );
    }

    render(<Harness />);

    const input = screen.getByLabelText("Target temperature");

    fireEvent.change(input, {
      target: { id: "target_temperature", value: "" },
    });

    expect(input).toHaveDisplayValue("");
  });

  test("DosingAutomationForm renders derived warnings from props and only reports user-driven changes", () => {
    const updateParent = jest.fn();

    render(
      <DosingAutomationForm
        fields={[
          { key: "duration", label: "Duration", type: "numeric", default: 30, unit: "min" },
          { key: "exchange_volume_ml", label: "Exchange volume", type: "numeric", default: 1.5, unit: "ml" },
        ]}
        description="Maintain a fixed dilution rate."
        updateParent={updateParent}
        name="chemostat"
        capacity={20}
        threshold={10}
        algoSettings={{
          duration: 30,
          exchange_volume_ml: 1.5,
          current_volume_ml: 11,
          efflux_tube_volume_ml: 18,
        }}
      />,
    );

    expect(updateParent).not.toHaveBeenCalled();
    expect(screen.getByText("Current volume exceeds safe maximum of 10 mL.")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Current volume"), {
      target: { id: "current_volume_ml", value: "9", valueAsNumber: 9 },
    });

    expect(updateParent).toHaveBeenCalledWith({ current_volume_ml: 9 });
  });

  test("DosingAutomationForm keeps cleared numeric inputs empty instead of restoring defaults", () => {
    function Harness() {
      const [algoSettings, setAlgoSettings] = React.useState({
        duration: 30,
        exchange_volume_ml: 1.5,
        current_volume_ml: 11,
        efflux_tube_volume_ml: 18,
      });

      return (
        <DosingAutomationForm
          fields={[
            { key: "duration", label: "Duration", type: "numeric", default: 30, unit: "min" },
            { key: "exchange_volume_ml", label: "Exchange volume", type: "numeric", default: 1.5, unit: "ml" },
          ]}
          description="Maintain a fixed dilution rate."
          updateParent={(partial) => setAlgoSettings((previous) => ({ ...previous, ...partial }))}
          name="chemostat"
          capacity={20}
          threshold={10}
          algoSettings={algoSettings}
        />
      );
    }

    render(<Harness />);

    const input = screen.getByLabelText("Duration");

    fireEvent.change(input, {
      target: { id: "duration", value: "" },
    });

    expect(input).toHaveDisplayValue("");
  });

  test("ChangeAutomationsDialog initializes defaults in the parent before start", async () => {
    renderWithSnackbar(
      <ChangeAutomationsDialog
        open
        onFinished={jest.fn()}
        unit="unit-1"
        experiment="exp-1"
        automationType="temperature"
      />,
    );

    await waitFor(() => expect(screen.getByLabelText("Target temperature")).toHaveValue(37));

    fireEvent.click(screen.getByText("Start"));

    expect(mockRunPioreactorJob).toHaveBeenCalledWith(
      "unit-1",
      "exp-1",
      "temperature_automation",
      [],
      {
        automation_name: "thermostat",
        skip_first_run: 0,
        target_temperature: 37,
        mode: "normal",
      },
      [],
    );
  });

  test("ChangeDosingAutomationsDialog initializes defaults in the parent before start", async () => {
    renderWithSnackbar(
      <ChangeDosingAutomationsDialog
        open
        onFinished={jest.fn()}
        unit="unit-1"
        experiment="exp-1"
        maxVolume={16}
        liquidVolume={14}
        capacity={20}
        threshold={18}
      />,
    );

    await waitFor(() => expect(screen.getByLabelText("Current volume")).toHaveValue(14));
    expect(screen.getByLabelText("Efflux tube level")).toHaveValue(16);

    fireEvent.click(screen.getByText("Start"));

    expect(mockRunPioreactorJob).toHaveBeenCalledWith(
      "unit-1",
      "exp-1",
      "dosing_automation",
      [],
      {
        automation_name: "chemostat",
        skip_first_run: 0,
        duration: 30,
        exchange_volume_ml: 1.5,
        current_volume_ml: 14,
        efflux_tube_volume_ml: 16,
      },
      [],
    );
  });
});
