import { createRoot } from "react-dom/client";
import { KioskProvider } from "./context";
import KioskErrorBoundary from "./ErrorBoundary";
import { KeyboardProvider } from "./Keyboard";
import KioskApp from "./KioskApp";
import { applyTheme, readTheme } from "./theme";
import { ConfirmProvider, ToastProvider } from "./ui";
import "./kiosk.css";

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
  <KioskErrorBoundary>
    <ToastProvider>
      <ConfirmProvider>
        <KeyboardProvider>
          <KioskProvider>
            <KioskApp />
          </KioskProvider>
        </KeyboardProvider>
      </ConfirmProvider>
    </ToastProvider>
  </KioskErrorBoundary>,
);
