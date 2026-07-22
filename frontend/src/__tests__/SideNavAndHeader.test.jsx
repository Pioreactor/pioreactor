import React from "react";
import { render, screen } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: { experiment: "experiment-a" },
    selectExperiment: jest.fn(),
    allExperiments: [],
  }),
}));

const { MemoryRouter } = require("react-router");
const SideNavAndHeaderModule = require("../components/SideNavAndHeader");
const SideNavAndHeader = SideNavAndHeaderModule.default;
const { pathnameMatchesAnySubmenu } = SideNavAndHeaderModule;

function renderSideNav(cameraUIEnabled) {
  return render(
    <MemoryRouter>
      <SideNavAndHeader cameraUIEnabled={cameraUIEnabled} />
    </MemoryRouter>,
  );
}

describe("pathnameMatchesAnySubmenu", () => {
  beforeEach(() => {
    global.fetch = jest.fn(() => new Promise(() => {}));
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("matches submenu routes directly from the current pathname", () => {
    expect(pathnameMatchesAnySubmenu("/leader", ["inventory", "leader", "system-logs"])).toBe(true);
    expect(pathnameMatchesAnySubmenu("/system-logs/unit-1", ["inventory", "leader", "system-logs"])).toBe(true);
    expect(pathnameMatchesAnySubmenu("/inventory", ["inventory", "leader", "system-logs"])).toBe(true);
  });

  test("does not open unrelated submenus", () => {
    expect(pathnameMatchesAnySubmenu("/overview", ["inventory", "leader", "system-logs"])).toBe(false);
    expect(pathnameMatchesAnySubmenu("/plugins", ["calibrations", "protocols", "estimators"])).toBe(false);
  });

  test("hides camera navigation when the camera UI is disabled", () => {
    renderSideNav(false);

    expect(screen.queryByText("Cameras")).not.toBeInTheDocument();
  });

  test("shows camera navigation when the camera UI is enabled", () => {
    renderSideNav(true);

    expect(screen.getAllByText("Cameras").length).toBeGreaterThan(0);
  });
});
