import { useSyncExternalStore } from "react";

// Pages live under /k/ with an implicit "self": the screen only ever shows the
// Pioreactor that serves it. /k/ is the home page.
const BASE = "/k";
const listeners = new Set();

function readPage() {
  const path = window.location.pathname;
  if (!path.startsWith(BASE)) return "";
  return decodeURIComponent(path.slice(BASE.length).replace(/^\/+|\/+$/g, ""));
}

function subscribe(listener) {
  listeners.add(listener);
  window.addEventListener("popstate", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("popstate", listener);
  };
}

export function usePage() {
  return useSyncExternalStore(subscribe, readPage);
}

// A kiosk has no back button, so navigation replaces the entry instead of
// growing the history.
export function navigate(page = "") {
  const url = page ? `${BASE}/${page}` : `${BASE}/`;
  if (window.location.pathname !== url) {
    window.history.replaceState(null, "", url);
    listeners.forEach((listener) => listener());
  }
}
