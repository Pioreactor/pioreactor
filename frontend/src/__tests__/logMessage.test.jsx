import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { parseLogMessage, splitTraceback } from "../utils/logMessage";

const mockSelectExperiment = jest.fn();

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    allExperiments: [{ experiment: "exp1" }],
    selectExperiment: mockSelectExperiment,
  }),
}));

const { MemoryRouter } = require("react-router");
const LogMessage = require("../components/LogMessage").default;

describe("parseLogMessage", () => {
  test("returns plain text when there are no backticks", () => {
    expect(parseLogMessage("stirring is blocking until disconnected.")).toEqual([
      { type: "text", text: "stirring is blocking until disconnected." },
    ]);
  });

  test("classifies spans by the preceding keyword", () => {
    const segments = parseLogMessage(
      "Saved calibration `od-cal-1`, estimator `fusion-1`, for experiment `exp 1` on worker `xr9`."
    );
    expect(segments.filter((segment) => segment.type !== "text")).toEqual([
      { type: "calibration", text: "od-cal-1" },
      { type: "estimator", text: "fusion-1" },
      { type: "experiment", text: "exp 1" },
      { type: "pioreactor", text: "xr9" },
    ]);
  });

  test("classifies plugins by the preceding keyword", () => {
    expect(parseLogMessage("Successfully installed plugin `relay-plugin`.")[1]).toEqual({
      type: "plugin",
      text: "relay-plugin",
    });
  });

  test("accepts plural keywords such as Worker(s)", () => {
    expect(parseLogMessage("Worker(s) `xr1` not found.")[1]).toEqual({ type: "pioreactor", text: "xr1" });
  });

  test("classifies known units and the row experiment without a keyword", () => {
    const segments = parseLogMessage("There exists profile actions for `xr1`, but it's not assigned to `exp1`.", {
      units: new Set(["xr1"]),
      experiment: "exp1",
    });
    expect(segments).toEqual([
      { type: "text", text: "There exists profile actions for " },
      { type: "pioreactor", text: "xr1" },
      { type: "text", text: ", but it's not assigned to " },
      { type: "experiment", text: "exp1" },
      { type: "text", text: "." },
    ]);
  });

  test("renders unknown spans as code", () => {
    expect(parseLogMessage("Executing `pio run stirring`.")[1]).toEqual({ type: "code", text: "pio run stirring" });
  });

  test("keeps messages with unbalanced backticks as plain text", () => {
    const message = "SQL that failed: `SELECT 1` with values `";
    expect(parseLogMessage(message)).toEqual([{ type: "text", text: message }]);
  });
});

describe("LogMessage", () => {
  test("renders entity chips and keeps the surrounding text", () => {
    const { container } = render(
      <MemoryRouter>
        <LogMessage message="Removed calibration `cal-1` from `xr1`." units={new Set(["xr1"])} />
      </MemoryRouter>
    );

    expect(container.querySelector('[data-calibration-name="cal-1"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "xr1" })).toHaveAttribute("href", "/pioreactors/xr1");
    expect(container.textContent).toBe("Removed calibration cal-1 from xr1.");
  });

  test("links known experiments to their overview and leaves unknown ones as labels", () => {
    render(
      <MemoryRouter>
        <LogMessage message="Moved from experiment `exp1` to experiment `deleted-exp`." />
      </MemoryRouter>
    );

    const experimentLink = screen.getByRole("link", { name: "exp1" });
    expect(experimentLink).toHaveAttribute("href", "/overview");
    fireEvent.click(experimentLink);
    expect(mockSelectExperiment).toHaveBeenCalledWith("exp1");
    expect(screen.queryByRole("link", { name: "deleted-exp" })).toBeNull();
  });

  test("links plugins to the Plugins page for the logging Pioreactor", () => {
    const { container, rerender } = render(
      <MemoryRouter>
        <LogMessage message="Successfully installed plugin `relay-plugin`." unit="xr1" />
      </MemoryRouter>
    );

    expect(container.querySelector('[data-plugin-name="relay-plugin"]')).not.toBeNull();
    expect(screen.getByRole("link", { name: "relay-plugin" })).toHaveAttribute("href", "/plugins/xr1");

    rerender(
      <MemoryRouter>
        <LogMessage message="Successfully installed plugin `relay-plugin`." />
      </MemoryRouter>
    );
    expect(screen.queryByRole("link", { name: "relay-plugin" })).toBeNull();
    expect(container.querySelector('[data-plugin-name="relay-plugin"]')).not.toBeNull();
  });
});

const LGPIO_TRACEBACK = [
  "Skipping LED / button controls: setup failed.",
  "Traceback (most recent call last):",
  '  File "/opt/pioreactor/venv/lib/python3.13/site-packages/pioreactor/background_jobs/monitor.py", line 181, in __init__',
  "    self._setup_GPIO()",
  "    ~~~~~~~~~~~~~~~~^^",
  "ModuleNotFoundError: No module named 'lgpio'",
].join("\n");

describe("splitTraceback", () => {
  test("leaves messages without a traceback alone", () => {
    expect(splitTraceback("Ready.")).toEqual({ summary: "Ready.", exceptionLine: null, traceback: null });
  });

  test("separates the summary, exception line, and a tidied traceback", () => {
    expect(splitTraceback(LGPIO_TRACEBACK)).toEqual({
      summary: "Skipping LED / button controls: setup failed.",
      exceptionLine: "ModuleNotFoundError: No module named 'lgpio'",
      traceback: [
        "Traceback (most recent call last):",
        '  File "pioreactor/background_jobs/monitor.py", line 181, in __init__',
        "    self._setup_GPIO()",
        "ModuleNotFoundError: No module named 'lgpio'",
      ].join("\n"),
    });
  });

  test("omits the exception line when the summary already says it", () => {
    const message = "Found extra property in setting `some_key`.\nTraceback (most recent call last):\n  File \"x.py\", line 1\nValueError: Found extra property in setting `some_key`.";
    expect(splitTraceback(message).exceptionLine).toBeNull();
  });
});

describe("LogMessage tracebacks", () => {
  test("hides the traceback behind a toggle", () => {
    render(
      <MemoryRouter>
        <LogMessage message={LGPIO_TRACEBACK} />
      </MemoryRouter>
    );

    expect(screen.getByText("ModuleNotFoundError: No module named 'lgpio'")).toBeInTheDocument();
    expect(screen.queryByText(/self\._setup_GPIO/)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Show traceback" }));
    expect(screen.getByText(/self\._setup_GPIO/)).toBeInTheDocument();
  });

  test("omits the traceback toggle when showTraceback is false", () => {
    render(
      <MemoryRouter>
        <LogMessage message={LGPIO_TRACEBACK} showTraceback={false} />
      </MemoryRouter>
    );

    expect(screen.getByText("ModuleNotFoundError: No module named 'lgpio'")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show traceback" })).toBeNull();
  });
});
