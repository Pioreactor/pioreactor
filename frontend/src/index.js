import React from 'react';
import './index.css';
import App from './App';
import "./styles.css";
import "./prism.css";

import { createRoot } from 'react-dom/client';


const PRELOAD_ERROR_RELOAD_AT_KEY = "pioreactor-ui-preload-error-reload-at";
const PRELOAD_ERROR_RELOAD_GUARD_MS = 30_000;

window.addEventListener("vite:preloadError", (event) => {
  const previousReloadAt = Number(window.sessionStorage.getItem(PRELOAD_ERROR_RELOAD_AT_KEY));

  if (Date.now() - previousReloadAt < PRELOAD_ERROR_RELOAD_GUARD_MS) {
    return;
  }

  event.preventDefault();
  window.sessionStorage.setItem(PRELOAD_ERROR_RELOAD_AT_KEY, String(Date.now()));
  window.location.reload();
});


// Only the leader serves /api. On any other unit, open this unit's page in the leader's UI instead.
fetch("/unit_api/health")
  .then((response) => (response.ok ? response.json() : {}))
  .then(({ leader_address: leaderAddress, pioreactor_unit: unit }) => {
    if (leaderAddress) {
      const url = new URL(`/pioreactors/${encodeURIComponent(unit)}`, window.location.href);
      url.hostname = leaderAddress;
      window.location.replace(url);
    }
  })
  .catch(() => {});


const container = document.getElementById('root');
const root = createRoot(container); // createRoot(container!) if you use TypeScript


root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
