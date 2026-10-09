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

Touchscreen display UI
-------

`display.html` is a second Vite entry (`src/display/`) for the leader's attached
5" landscape touchscreen (designed at 800x480, rendered by WPE on a Pi; see
`packaging/experimental/display/`). It is served at `/static/display.html` and is
deliberately separate from the main app's pages and MUI layout.

- Reuse the main app's data layer (providers, `utils/`, hooks, API calls) and its
  icons; only the views are display-specific.
- Touch only: no hover states or tooltips. Targets are at least 44px and give
  feedback through `:active`/pending states. Avoid shadows, blurs, transitions and
  animations; the display can be laggy.
- Text and number entry go through the pop-up keyboard (`useKeyboard` / `EditField`
  in `src/display/Keyboard.jsx`), never a native input.
- Develop at `http://localhost:3000/display.html` with the browser viewport set to 800x480.
