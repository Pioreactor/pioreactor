import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SnackbarProvider } from "notistack";
import UsbDriveCard from "../components/UsbDriveCard";
import { fetchTaskResult } from "../utils/tasks";

jest.mock("../utils/tasks", () => ({ fetchTaskResult: jest.fn() }));

test.each([false, true])("leader USB mutation carries target identity (mounted=%s)", async (mounted) => {
  fetchTaskResult.mockReset().mockResolvedValue({});
  global.fetch = jest.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      partitions: [{ device: "/dev/sda1", display_name: "Drive", mounted }],
    }),
  });
  render(<SnackbarProvider><UsbDriveCard leaderHostname="leader-unit" /></SnackbarProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "More actions for Drive" }));
  fireEvent.click(screen.getByRole("menuitem", { name: mounted ? "Eject" : "Mount" }));

  await waitFor(() => expect(fetchTaskResult).toHaveBeenCalledWith(
    `/unit_api/usb/${mounted ? "eject" : "mount"}`,
    expect.objectContaining({
      fetchOptions: {
        method: "POST",
        body: JSON.stringify({ device: "/dev/sda1" }),
        headers: {
          "X-Pioreactor-Target": "leader-unit",
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      },
    }),
  ));
  await screen.findByText(mounted ? "USB drive ejected." : "USB drive mounted.");
});
