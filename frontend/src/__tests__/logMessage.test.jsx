import React from "react";
import { render, screen } from "@testing-library/react";
import { parseLogMessage } from "../utils/logMessage";

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
});
