**frontend directory summary**

*   **Purpose**: A React-based frontend for the Pioreactor system. It offers multiple pages (e.g., overview, plugins, calibrations, data export) with real-time interactions using MQTT and REST APIs.

*   **Development Workflow**: The README describes how to run the project in development (`npm run start`) or build for production (`npm run build`).

*   **Build Configuration**: `package.json` lists dependencies such as React 19, MUI, mqtt.js, js-yaml, etc., along with scripts for starting, building, linting, and testing the app.

*   **Main Application**: `App.jsx` sets up MUI theming and React Router routes for pages like `/overview`, `/pioreactors`, `/export-data`, `/plugins`, and more.

*   **MQTT Integration**: `MQTTContext.js` establishes an MQTT client with a fallback strategy for multiple brokers, using a trie structure to manage topic handlers. It exposes `subscribeToTopic` and `unsubscribeFromTopic` through a React context and displays a Snackbar on connection errors.

*   **Utilities**: `src/utils/` contains focused helper modules such as `config.js` for `getConfig`, `jobs.js` for `runPioreactorJob`, `tasks.js` for retryable task-result polling, and `color.js` for color constants and `ColorCycler`.

*   **Feature Example**: `ExperimentProfileEditor.jsx` lets users create or edit experiment profiles in YAML, save them through the API, and preview parsed results in real time. `CreateExperimentProfile.jsx` and `EditExperimentProfile.jsx` are the route-level wrappers.
    `ExportData.jsx` lets users pick datasets and experiments, preview samples, and download results through the routes under `/api/datasets/exportable`.

*   **Styling and Assets**: Includes `styles.css`, `index.css`, and public images/logos. The UI uses MUI components for theming and layout.

*   **Overall Design**: The project follows a modular React structure with many components under `src/components/`. State management relies on custom React contexts (e.g., MQTTProvider, ExperimentProvider). MQTT provides real-time updates for Pioreactor units, while REST endpoints supply configuration and experimental data.


This repository presents a modern React single-page application tailored to manage and monitor Pioreactor devices, leveraging MQTT for realtime communication and MUI for interface components.

Rules
-------

1. Keep imports at the top of the file
2. Reference DESIGN.md for visual and interaction design rules
3. Keep React and ESLint warnings green. Before wrapping up frontend work, run the relevant lint command or `make frontend-build` and fix simple warnings instead of leaving them behind.

Per-Pioreactor touchscreen UI ("kiosk")
-------

`kiosk.html` is a second Vite entry (`src/kiosk/`) for the touchscreen on each
Pioreactor (5" 1280x720 at 1x, rendered by WPE on a Pi). Pages live under `/k/`
and always show the Pioreactor serving them. `KIOSK.md` holds the product
direction, decisions, and open questions.

- It's deliberately lean: no MUI or emotion at runtime (icons are plain SVG in
  `src/kiosk/icons.jsx`), its own MQTT client that reconnects forever
  (`src/kiosk/mqtt.js`), and plain CSS in `src/kiosk/kiosk.css`.
- Unit-local actions go to the unit's own `/unit_api`; cluster data comes from the
  leader's `/api` via `leaderApi()` (cross-origin on workers). Running jobs'
  settings change by publishing `.../<setting>/set` over MQTT.
- Touch only: no hover states or tooltips. Targets are at least `--target`
  (3.4rem, about 9 mm on the panel) and give feedback through `:active`/pending
  states. Avoid shadows, blurs, transitions and animations.
- Text and number entry go through the pop-up keyboard (`useKeyboard` /
  `EditField` in `src/kiosk/Keyboard.jsx`), never a native input.
- Develop at `http://localhost:3000/k/` with the browser viewport set to 1280x720.
