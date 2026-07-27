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
    experimentMetadata: {},
    selectExperiment: jest.fn(),
    allExperiments: [],
  }),
}));

const React = require("react");
const { act, cleanup, render, screen } = require("@testing-library/react");
const { MemoryRouter } = require("react-router");
const SideNavAndHeaderModule = require("../components/SideNavAndHeader");
const SideNavAndHeader = SideNavAndHeaderModule.default;
const { pathnameMatchesAnySubmenu } = SideNavAndHeaderModule;

const originalFetch = global.fetch;
const originalResizeObserver = global.ResizeObserver;
const originalDocumentHidden = Object.getOwnPropertyDescriptor(document, "hidden");

let documentIsHidden = false;

function renderSideNavAndHeader(cameraUIEnabled = false) {
  return render(
    <MemoryRouter initialEntries={["/overview"]}>
      <SideNavAndHeader cameraUIEnabled={cameraUIEnabled} />
    </MemoryRouter>,
  );
}

function getUsbStatusRequestCount() {
  return global.fetch.mock.calls.filter(([url]) => url === "/unit_api/usb").length;
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

function setDocumentHidden(hidden) {
  documentIsHidden = hidden;
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
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
    renderSideNavAndHeader(false);

    expect(screen.queryByText("Cameras")).not.toBeInTheDocument();
  });

  test("shows camera navigation when the camera UI is enabled", () => {
    renderSideNavAndHeader(true);

    expect(screen.getAllByText("Cameras").length).toBeGreaterThan(0);
  });
});

describe("USB status polling", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    documentIsHidden = false;
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => documentIsHidden,
    });
    global.ResizeObserver = jest.fn(() => ({
      observe: jest.fn(),
      unobserve: jest.fn(),
      disconnect: jest.fn(),
    }));
    global.fetch = jest.fn((url) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(url === "/unit_api/usb" ? { status: "absent" } : {}),
      }),
    );
  });

  afterEach(() => {
    cleanup();
    jest.useRealTimers();
    global.fetch = originalFetch;
    global.ResizeObserver = originalResizeObserver;
    if (originalDocumentHidden) {
      Object.defineProperty(document, "hidden", originalDocumentHidden);
    } else {
      delete document.hidden;
    }
  });

  test("polls while visible, pauses while hidden, and refreshes on return", async () => {
    renderSideNavAndHeader();
    await flushPromises();

    expect(getUsbStatusRequestCount()).toBe(1);

    act(() => {
      jest.advanceTimersByTime(15000);
    });
    await flushPromises();
    expect(getUsbStatusRequestCount()).toBe(2);

    setDocumentHidden(true);
    act(() => {
      jest.advanceTimersByTime(45000);
    });
    await flushPromises();
    expect(getUsbStatusRequestCount()).toBe(2);

    setDocumentHidden(false);
    await flushPromises();
    expect(getUsbStatusRequestCount()).toBe(3);

    act(() => {
      jest.advanceTimersByTime(30000);
    });
    await flushPromises();
    expect(getUsbStatusRequestCount()).toBe(5);
  });

  test("does not fetch when mounted hidden until the document becomes visible", async () => {
    documentIsHidden = true;

    renderSideNavAndHeader();
    await flushPromises();
    act(() => {
      jest.advanceTimersByTime(45000);
    });
    await flushPromises();

    expect(getUsbStatusRequestCount()).toBe(0);

    setDocumentHidden(false);
    await flushPromises();

    expect(getUsbStatusRequestCount()).toBe(1);
  });

  test("removes USB polling and visibility handling when unmounted", async () => {
    const { unmount } = renderSideNavAndHeader();
    await flushPromises();

    expect(getUsbStatusRequestCount()).toBe(1);

    unmount();
    setDocumentHidden(true);
    setDocumentHidden(false);
    act(() => {
      jest.advanceTimersByTime(30000);
    });
    await flushPromises();

    expect(getUsbStatusRequestCount()).toBe(1);
  });
});
