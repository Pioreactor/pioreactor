import { createContext, useContext } from "react";

export const DisplayContext = createContext(null);
export const useDisplay = () => useContext(DisplayContext);

// Routes live in the hash (#/unit/pio01) so a reload keeps the current screen.
export function navigate(screen, param) {
  window.location.hash = param ? `/${screen}/${encodeURIComponent(param)}` : `/${screen}`;
}
