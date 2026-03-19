import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";

import { TimeFormatSwitch, TimeWindowSwitch } from "../components/TimeControls";

describe("TimeControls", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  test("TimeFormatSwitch reports user changes and persists them", () => {
    const setTimeScale = jest.fn();
    const { rerender } = render(
      <TimeFormatSwitch timeScale="hours" setTimeScale={setTimeScale} />,
    );

    expect(setTimeScale).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Elapsed time" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Timestamp" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "Timestamp" }));

    expect(setTimeScale).toHaveBeenCalledWith("clock_time");
    expect(window.localStorage.getItem("timeScale")).toBe("clock_time");

    rerender(<TimeFormatSwitch timeScale="clock_time" setTimeScale={setTimeScale} />);

    expect(screen.getByRole("button", { name: "Elapsed time" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Timestamp" })).toHaveAttribute("aria-pressed", "true");
  });

  test("TimeWindowSwitch reports user changes and follows parent state", () => {
    const setTimeWindow = jest.fn();
    const { rerender } = render(
      <TimeWindowSwitch timeWindow={1000000} setTimeWindow={setTimeWindow} />,
    );

    expect(setTimeWindow).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "All time" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Past hour" })).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(screen.getByRole("button", { name: "Past hour" }));

    expect(setTimeWindow).toHaveBeenCalledWith(1);
    expect(window.localStorage.getItem("timeWindow")).toBe("1");

    rerender(<TimeWindowSwitch timeWindow={1} setTimeWindow={setTimeWindow} />);

    expect(screen.getByRole("button", { name: "All time" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Past hour" })).toHaveAttribute("aria-pressed", "true");
  });
});
