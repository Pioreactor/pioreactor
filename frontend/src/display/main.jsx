import { createRoot } from "react-dom/client";
import { SnackbarProvider } from "notistack";
import { applyTheme, readTheme } from "./theme";
import DisplayApp from "./DisplayApp";
import DisplayErrorBoundary from "./ErrorBoundary";
import "./display.css";

applyTheme(readTheme());

// Hide the pointer while the screen is driven by touch; show it again for a mouse.
document.addEventListener(
  "pointerdown",
  (event) => document.documentElement.classList.toggle("touch", event.pointerType === "touch"),
  { capture: true, passive: true },
);
// WebKit only applies :active on touch when a touch listener exists.
document.addEventListener("touchstart", () => {}, { passive: true });
// Long-press would otherwise open a context menu.
document.addEventListener("contextmenu", (event) => event.preventDefault());

createRoot(document.getElementById("root")).render(
  <SnackbarProvider maxSnack={2} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
    <DisplayErrorBoundary>
      <DisplayApp />
    </DisplayErrorBoundary>
  </SnackbarProvider>,
);
