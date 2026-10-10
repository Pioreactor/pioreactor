import { darkColors, lightColors } from "../theme/colors";

const THEME_KEY = "pioreactor-kiosk-theme";

export function readTheme() {
  try {
    return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch (_error) {
    return "light";
  }
}

// Shares the main UI's colour definitions (theme/colors.js) as --ui-* variables.
export function applyTheme(mode) {
  const root = document.documentElement;
  const palette = mode === "dark" ? { ...lightColors, ...darkColors } : lightColors;
  for (const [name, value] of Object.entries(palette)) {
    root.style.setProperty(`--ui-${name}`, value);
  }
  root.dataset.theme = mode;
  try {
    window.localStorage.setItem(THEME_KEY, mode);
  } catch (_error) {
    // storage may be unavailable; the theme still applies until the next reload
  }
}
