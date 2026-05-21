import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import RecordEventLogDialog from "../components/RecordEventLogDialog";

function renderRecordEventLogDialog(onSubmit) {
  return render(
    <RecordEventLogDialog
      defaultPioreactor="unit1"
      defaultExperiment="exp1"
      availableUnits={["unit1"]}
      onSubmit={onSubmit}
    />
  );
}

describe("RecordEventLogDialog", () => {
  test("closes and clears fields after a successful submit", async () => {
    const user = userEvent.setup();
    const onSubmit = jest.fn().mockResolvedValue(undefined);

    renderRecordEventLogDialog(onSubmit);

    await user.click(screen.getByRole("button", { name: /record new event/i }));
    await user.type(screen.getByRole("textbox", { name: /message/i }), "Added fresh media");
    await user.type(screen.getByRole("textbox", { name: /source/i }), "manual");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        pioreactor_unit: "unit1",
        experiment: "exp1",
        message: "Added fresh media",
        task: "manual",
        source: "UI",
        level: "INFO",
      })
    );
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /record new event/i }));
    expect(screen.getByRole("textbox", { name: /message/i })).toHaveValue("");
    expect(screen.getByRole("textbox", { name: /source/i })).toHaveValue("");
  });

  test("keeps typed fields visible and shows an inline error after failed submit", async () => {
    const user = userEvent.setup();
    const onSubmit = jest.fn().mockRejectedValue(new Error("Worker is unreachable."));

    renderRecordEventLogDialog(onSubmit);

    await user.click(screen.getByRole("button", { name: /record new event/i }));
    await user.type(screen.getByRole("textbox", { name: /message/i }), "Do not lose this");
    await user.type(screen.getByRole("textbox", { name: /source/i }), "operator");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(await screen.findByText("Worker is unreachable.")).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: /message/i })).toHaveValue("Do not lose this");
    expect(screen.getByRole("textbox", { name: /source/i })).toHaveValue("operator");
    expect(screen.getByRole("button", { name: "Submit" })).toBeEnabled();
  });

  test("does not allow a second submit while the first request is in flight", async () => {
    const user = userEvent.setup();
    let resolveSubmit;
    const onSubmit = jest.fn(
      () =>
        new Promise((resolve) => {
          resolveSubmit = resolve;
        })
    );

    renderRecordEventLogDialog(onSubmit);

    await user.click(screen.getByRole("button", { name: /record new event/i }));
    await user.type(screen.getByRole("textbox", { name: /message/i }), "Only submit once");
    await user.click(screen.getByRole("button", { name: "Submit" }));

    expect(screen.getByRole("button", { name: "Submitting..." })).toBeDisabled();
    expect(onSubmit).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveSubmit();
    });
  });
});
