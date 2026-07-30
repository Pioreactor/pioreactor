import React from "react";
import { render, screen } from "@testing-library/react";

import ErrorBoundary from "../components/ErrorBoundary";


const mockRender = jest.fn();

jest.mock("react-dom/client", () => ({
  ...jest.requireActual("react-dom/client"),
  createRoot: (container) => {
    if (container.id === "root") {
      return { render: mockRender };
    }
    return jest.requireActual("react-dom/client").createRoot(container);
  },
}));

jest.mock("../App", () => () => null);


function BrokenPage() {
  throw new Error("Failed to fetch dynamically imported module");
}


describe("stale frontend build recovery", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    jest.spyOn(console, "error").mockImplementation(() => {});
    jest.spyOn(console, "log").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("reloads only once for preload errors during the guard window", () => {
    jest.spyOn(Date, "now").mockReturnValue(1_000_000);
    document.body.innerHTML = '<div id="root"></div>';

    jest.isolateModules(() => {
      require("../index");
    });

    const firstError = new Event("vite:preloadError", { cancelable: true });
    window.dispatchEvent(firstError);

    expect(firstError.defaultPrevented).toBe(true);
    expect(window.sessionStorage.getItem("pioreactor-ui-preload-error-reload-at")).toBe("1000000");

    const repeatedError = new Event("vite:preloadError", { cancelable: true });
    window.dispatchEvent(repeatedError);

    expect(repeatedError.defaultPrevented).toBe(false);
  });

  test("offers a manual reload when automatic recovery falls through", () => {
    render(
      <ErrorBoundary>
        <BrokenPage />
      </ErrorBoundary>,
    );

    expect(
      screen.getByText("If Pioreactor was just updated, reload this page to use the new UI."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload Pioreactor UI" })).toBeInTheDocument();
  });
});
