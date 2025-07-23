**frontend directory summary**

*   **Purpose**: A React-based frontend for the Pioreactor system. It offers multiple pages (e.g., overview, plugins, calibrations, data export) with real-time interactions using MQTT and REST APIs.

*   **Development Workflow**: The README describes how to run the project in development (`npm run start`) or build for production (`npm run build`).

*   **Build Configuration**: `package.json` lists dependencies such as React 18, Material-UI, mqtt.js, js-yaml, etc., along with scripts for starting, building, linting, and testing the app.

*   **Main Application**: `App.jsx` sets up Material-UI theming and React Router routes for pages like `/overview`, `/pioreactors`, `/export-data`, `/plugins`, and more.

*   **MQTT Integration**: `MQTTContext.js` establishes an MQTT client with a fallback strategy for multiple brokers, using a trie structure to manage topic handlers. It exposes `subscribeToTopic` and `unsubscribeFromTopic` through a React context and displays a Snackbar on connection errors.

*   **Utilities**: `utilities.js` provides helper functions such as `getConfig`, `runPioreactorJob`, and a retryable `checkTaskCallback`. It also defines color constants and a `ColorCycler` class.

*   **Feature Example**: `CreateExperimentProfile.jsx` allows users to author experiment profiles in YAML using a code editor, save them via an API call, and preview parsed results in real time.
    `ExportData.jsx` lets users pick datasets and experiments, preview samples, and download results via `/api/export_datasets`.

*   **Styling and Assets**: Includes `styles.css`, `index.css`, and public images/logos. The UI uses Material-UI components for theming and layout.

*   **Overall Design**: The project follows a modular React structure with many components under `src/components/`. State management relies on custom React contexts (e.g., MQTTProvider, ExperimentProvider). MQTT provides real-time updates for Pioreactor units, while REST endpoints supply configuration and experimental data.


This repository presents a modern React single-page application tailored to manage and monitor Pioreactor devices, leveraging MQTT for realtime communication and Material-UI for interface components.
