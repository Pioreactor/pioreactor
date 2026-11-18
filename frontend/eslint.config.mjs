import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import unusedImports from "eslint-plugin-unused-imports";

export default [
  {
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    languageOptions: {
      globals: { ...globals.browser, ...globals.jest },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: {
      "react-hooks": reactHooks,
      "unused-imports": unusedImports,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "unused-imports/no-unused-imports": "warn",
      "unused-imports/no-unused-vars": [
        "warn",
        {
          vars: "all",
          varsIgnorePattern: "^_",
          args: "after-used",
          argsIgnorePattern: "^(?:_.*|e|err|error)$",
          caughtErrors: "all",
          caughtErrorsIgnorePattern: "^(?:_.*|e|err|error)$",
        },
      ],
    },
  },
  {
    files: ["src/kiosk/**/*.{js,jsx}"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@mui/*", "@emotion/*", "victory", "victory-*"],
              message: "The touchscreen UI stays free of MUI, emotion and Victory at runtime (render cost on WPE). Use plain CSS, plain SVG icons and canvas charts.",
            },
            {
              group: ["**/providers/MQTTContext"],
              message: "The touchscreen UI uses its own MQTT client, which reconnects forever.",
            },
          ],
        },
      ],
    },
  },
];
