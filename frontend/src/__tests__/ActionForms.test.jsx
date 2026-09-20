import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { SnackbarProvider } from "notistack";
import ActionLEDForm from "../components/ActionLEDForm";
import ActionCirculatingForm from "../components/ActionCirculatingForm";

describe("Hardware action forms", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  test("rejects malformed LED decimals and submits a valid intensity", () => {
    global.fetch.mockResolvedValue({ ok: true });
    render(
      <SnackbarProvider>
        <ActionLEDForm unit="worker1" experiment="experiment1" channel="A" />
      </SnackbarProvider>,
    );
    const input = screen.getByRole("textbox", { name: /intensity/i });
    const update = screen.getByRole("button", { name: "Update" });

    for (const value of ["12.5.6", "10..5", ".", "101", "-1"]) {
      fireEvent.change(input, { target: { value } });
      expect(update).toBeDisabled();
      expect(input).toHaveAttribute("aria-invalid", "true");
    }
    expect(global.fetch).not.toHaveBeenCalled();

    for (const value of ["0", "100", ".5", "12.5"]) {
      fireEvent.change(input, { target: { value } });
      expect(update).toBeEnabled();
    }
    fireEvent.click(update);
    expect(JSON.parse(global.fetch.mock.calls[0][1].body).options.A).toBe(12.5);
  });

  test("shows feedback when the circulation Stop request receives an HTTP error", async () => {
    global.fetch.mockResolvedValue({ ok: false, status: 500 });
    render(
      <SnackbarProvider>
        <ActionCirculatingForm
          unit="worker1"
          experiment="experiment1"
          action="circulate_media"
          job={{ state: "ready" }}
        />
      </SnackbarProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/failed to stop/i);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/workers/worker1/jobs/stop/job_name/circulate_media/experiments/experiment1",
      { method: "POST" },
    );
  });
});
