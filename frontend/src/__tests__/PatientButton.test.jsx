import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import PatientButton from "../components/PatientButton";

describe("PatientButton", () => {
  test("renders prop updates directly without syncing local text state", () => {
    const { rerender } = render(<PatientButton buttonText="Start" />);

    expect(screen.getByRole("button", { name: "Start" })).toBeInTheDocument();

    rerender(<PatientButton buttonText="Pause" />);

    expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument();
  });

  test("shows a spinner while an async click is pending and keeps it until the prop label updates", async () => {
    let resolveClick;
    const onClick = jest.fn(
      () =>
        new Promise((resolve) => {
          resolveClick = resolve;
        }),
    );

    const { rerender } = render(<PatientButton buttonText="Start" onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("progressbar")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();

    resolveClick();

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    rerender(<PatientButton buttonText="Pause" onClick={onClick} />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument());
  });

  test("keeps the spinner visible until buttonText changes after a successful click", async () => {
    const onClick = jest.fn(() => Promise.resolve());
    const { rerender } = render(<PatientButton buttonText="Start" onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    rerender(<PatientButton buttonText="Pause" onClick={onClick} />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Pause" })).toBeInTheDocument());
  });

  test("shows error feedback and a retry label after a failed click", async () => {
    const onClick = jest.fn(() => Promise.reject(new Error("Failed to start")));

    render(<PatientButton buttonText="Start" onClick={onClick} />);

    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    expect(await screen.findByText("Failed to start")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
