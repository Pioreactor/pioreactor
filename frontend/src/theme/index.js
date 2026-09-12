import { createTheme } from "@mui/material/styles";
import { lightColors, darkColors } from "./colors";

const theme = createTheme({
  focusVisible: true,
  cssVariables: { colorSchemeSelector: "data" },
  colorSchemes: {
    light: {
      palette: {
        background: { default: "#f6f6f7" },
        primary: { main: "#5331CA" },
        secondary: { main: "#DF1A0C" },
        ui: lightColors,
      },
    },
    dark: {
      palette: {
        background: { default: "#191a21", paper: darkColors.surface },
        primary: { main: darkColors.primary },
        secondary: { main: "#ff9387" },
        text: { primary: darkColors.text, secondary: darkColors.textSecondary },
        ui: darkColors,
      },
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: (theme) => ({
        ...theme.applyStyles("dark", {
          "a:not([class])": { color: darkColors.primary },
        }),
      }),
    },
    MuiAppBar: {
      styleOverrides: {
        root: ({ theme }) => theme.applyStyles("dark", {
          backgroundColor: "#30254f",
          color: darkColors.text,
          backgroundImage: "none",
        }),
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: ({ theme }) => theme.applyStyles("dark", { backgroundImage: "none" }),
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: "none",
        },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          textTransform: "none",
        },
      },
    },
  },
});

export default theme;
