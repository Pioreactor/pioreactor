// Shared UI colours. Data-series and illustration colours remain with their owners.
export const lightColors = {
  "surface": "white",
  "stripe": "#F7F7F7",
  "primary": "#5331ca",
  "selection": "#5331ca14",
  "text": "rgba(0, 0, 0, 0.87)",
  "textSecondary": "rgba(0, 0, 0, 0.60)",
  "navDisabled": "#00000050",
  "navIcon": "rgb(75, 75, 75)",
  "codeBackground": "rgba(0, 0, 0, 0.07)",
  "subtleBackground": "#f3f3f3",
  "selectedSurface": "#f6f4fa",
  "hoverSurface": "#f9f9f9",
  "chartControl": "rgba(255,255,255,0.85)",
  "ready": "#176114",
  "readyBackground": "#DDFFDC",
  "disconnected": "#585858",
  "lost": "#DE3618",
  "lostBackground": "#fbeae9",
  "stateBackground": "rgba(0, 0, 0, 0.04)",
  "disabled": "rgba(0, 0, 0, 0.38)",
  "inactive": "#99999b",
  "logError": "#FF8F7B",
  "logWarning": "#ffefa4",
  "logNotice": "#addcaf",
  "editorBackground": "rgb(248,248,248)",
  "border": "#ccc"
};


export const darkColors = {
  surface: "#22232b",
  stripe: "#292a34",
  primary: "#b9a5ff",
  selection: "#b9a5ff24",
  text: "#f1f0f5",
  textSecondary: "#bdbbc9",
  navDisabled: "#777581",
  navIcon: "#c9c6d6",
  codeBackground: "#ffffff12",
  subtleBackground: "#30313c",
  selectedSurface: "#302b43",
  hoverSurface: "#2c2d38",
  chartControl: "rgba(34,35,43,0.85)",
  ready: "#8ddc94",
  readyBackground: "#233d2b",
  disconnected: "#b8b5c3",
  lost: "#ff9a8e",
  lostBackground: "#492c30",
  stateBackground: "#ffffff0f",
  disabled: "#ffffff61",
  inactive: "#a3a0ae",
  logError: "#673831",
  logWarning: "#514622",
  logNotice: "#2c4b37",
  editorBackground: "#22232b",
  border: "#55535f",
};

// CSS references also work in plain styles and module-level status definitions.
// Light fallbacks keep standalone components usable outside the app provider.
export const uiColors = Object.fromEntries(
  Object.entries(lightColors).map(([name, value]) => [
    name, `var(--mui-palette-ui-${name}, ${value})`,
  ]),
);
