import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider } from "@mui/material/styles";
import AppearanceMenu from "../components/AppearanceMenu";
import theme from "../theme";

let systemDark;
let mediaListeners;
const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  localStorage.clear();
  systemDark = false;
  mediaListeners = new Set();
  window.matchMedia = jest.fn(() => ({
    get matches() { return systemDark; },
    addListener: (listener) => mediaListeners.add(listener),
    removeListener: (listener) => mediaListeners.delete(listener),
  }));
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  document.documentElement.removeAttribute("data-dark");
  document.documentElement.removeAttribute("data-light");
});

function renderAppearance() {
  return render(
    <ThemeProvider theme={theme} defaultMode="light" modeStorageKey="pioreactor-color-mode">
      <AppearanceMenu />
      <input aria-label="Draft" defaultValue="Unsaved work" />
    </ThemeProvider>,
  );
}

async function chooseMode(user, mode) {
  await user.click(screen.getByRole("button", { name: "Appearance" }));
  await user.click(screen.getByRole("menuitemradio", { name: mode, exact: true }));
}

test("switches modes without remounting content, remembers the choice, and restores focus", async () => {
  const user = userEvent.setup();
  const { unmount } = renderAppearance();
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-light"));
  const draft = screen.getByRole("textbox", { name: "Draft" });
  await user.type(draft, " in progress");

  await chooseMode(user, "Dark");
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-dark"));
  expect(localStorage.getItem("pioreactor-color-mode")).toBe("dark");
  expect(screen.getByRole("textbox", { name: "Draft" })).toBe(draft);
  expect(draft).toHaveValue("Unsaved work in progress");
  await waitFor(() => expect(screen.getByRole("button", { name: "Appearance" })).toHaveFocus());

  unmount();
  renderAppearance();
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-dark"));
  await chooseMode(user, "Light");
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-light"));
});

test("System follows preference changes; an explicit choice overrides them", async () => {
  const user = userEvent.setup();
  renderAppearance();
  await chooseMode(user, "System");
  act(() => {
    systemDark = true;
    mediaListeners.forEach((listener) => listener({ matches: true }));
  });
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-dark"));
  expect(localStorage.getItem("pioreactor-color-mode")).toBe("system");

  await chooseMode(user, "Light");
  act(() => mediaListeners.forEach((listener) => listener({ matches: true })));
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-light"));
});

test("the menu supports keyboard selection and Escape dismissal", async () => {
  const user = userEvent.setup();
  renderAppearance();
  await user.tab();
  await user.keyboard("{Enter}");
  expect(screen.getByRole("menuitemradio", { name: "Light", exact: true })).toHaveAttribute("aria-checked", "true");
  await user.keyboard("{ArrowDown}{Enter}");
  await waitFor(() => expect(document.documentElement).toHaveAttribute("data-dark"));
  await user.keyboard("{Enter}{Escape}");
  await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Appearance" })).toHaveFocus();
});
