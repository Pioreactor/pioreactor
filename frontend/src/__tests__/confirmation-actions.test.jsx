import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfirmProvider } from "material-ui-confirm";
import { MemoryRouter } from "react-router";
import { ButtonStopProcess } from "../components/PioreactorCardShared";
import ManageInventoryMenu from "../components/ManageInventoryMenu";

describe("confirmation actions with the real v4 provider", () => {
  beforeEach(() => {
    global.fetch = jest.fn().mockResolvedValue({ ok: true });
  });

  test.each([undefined, "unit-1"])("only stops %s after explicit confirmation", async (unit) => {
    const user = userEvent.setup();
    render(
      <ConfirmProvider>
        <ButtonStopProcess unit={unit} experiment="experiment a" />
      </ConfirmProvider>,
    );
    await user.click(screen.getByRole("button", { name: unit ? "Stop" : "Stop all Pioreactors" }));
    expect(global.fetch).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      `/api/workers/${unit || "$broadcast"}/jobs/stop/experiments/experiment%20a`,
      { method: "POST" },
    ));
  });

  test.each(["cancel", "escape", "backdrop", "unmount"])(
    "does not stop on %s",
    async (outcome) => {
      const user = userEvent.setup();
      const view = render(
        <ConfirmProvider>
          <ButtonStopProcess experiment="experiment a" />
        </ConfirmProvider>,
      );
      await user.click(screen.getByRole("button", { name: "Stop all Pioreactors" }));
      if (outcome === "cancel") {
        await user.click(screen.getByRole("button", { name: "Cancel" }));
      } else if (outcome === "escape") {
        await user.keyboard("{Escape}");
      } else if (outcome === "backdrop") {
        await user.click(screen.getByRole("dialog").parentElement);
      } else {
        view.rerender(<ConfirmProvider>{null}</ConfirmProvider>);
        await act(async () => {});
      }
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(global.fetch).not.toHaveBeenCalled();
    },
  );

  test.each(["Reboot all workers", "Shutdown all workers", "Unassign all workers"])(
    "canceling %s does not send a request or navigate",
    async (action) => {
      const user = userEvent.setup();
      render(
        <MemoryRouter>
          <ConfirmProvider>
            <ManageInventoryMenu />
          </ConfirmProvider>
        </MemoryRouter>,
      );
      await user.click(screen.getByRole("button", { name: /Manage inventory/ }));
      await user.click(screen.getByRole("menuitem", { name: action }));
      await user.click(screen.getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(global.fetch).not.toHaveBeenCalled();
    },
  );
});
