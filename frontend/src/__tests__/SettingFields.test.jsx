import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingNumericField, SettingTextField } from "../components/PioreactorCardShared";

function settingCallbacks() {
  return {
    onUpdate: jest.fn(),
    setSnackbarMessage: jest.fn(),
    setSnackbarOpen: jest.fn(),
  };
}

test("Cancel restores the latest numeric value and clears validation and focus", async () => {
  const user = userEvent.setup();
  const callbacks = settingCallbacks();
  const { rerender } = render(<SettingNumericField value={500} min={100} {...callbacks} />);
  const input = screen.getByRole("spinbutton");
  const update = screen.getByRole("button", { name: "Update" });
  expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();

  await user.click(input);
  fireEvent.change(input, { target: { value: "55" } });
  expect(input).toBeInvalid();
  expect(update).toBeDisabled();

  rerender(<SettingNumericField value={525} min={100} {...callbacks} />);
  expect(input).toHaveValue(55);
  expect(input).toHaveFocus();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(input).toHaveValue(525);
  expect(input).toBeValid();
  expect(input).not.toHaveFocus();
  expect(update).toBeDisabled();
  expect(callbacks.onUpdate).not.toHaveBeenCalled();
  expect(callbacks.setSnackbarOpen).not.toHaveBeenCalled();
});

test("keyboard activation of Cancel discards a text draft and prevents submitting it", async () => {
  const user = userEvent.setup();
  const callbacks = settingCallbacks();
  render(<SettingTextField value="Original label" {...callbacks} />);
  const input = screen.getByRole("textbox");
  await user.clear(input);
  await user.type(input, "Draft");
  await user.tab();
  await user.tab();
  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  await user.keyboard("{Enter}");

  expect(input).toHaveValue("Original label");
  expect(input).not.toHaveFocus();
  expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  await user.click(input);
  await user.keyboard("{Enter}");
  expect(callbacks.onUpdate).not.toHaveBeenCalled();
});
