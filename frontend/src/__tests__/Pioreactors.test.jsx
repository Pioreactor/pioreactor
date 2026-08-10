import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const mockNavigate = jest.fn();
const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
let mockExperimentMetadata = { experiment: "exp1" };

jest.mock("react-router", () => {
  const actual = jest.requireActual("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    experimentMetadata: mockExperimentMetadata,
    allExperiments: [mockExperimentMetadata],
    selectExperiment: jest.fn(),
    setAllExperiments: jest.fn(),
    updateExperiment: jest.fn(),
  }),
}));

jest.mock("notistack", () => ({
  useSnackbar: () => ({
    enqueueSnackbar: jest.fn(),
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: {},
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

const { MemoryRouter } = require("react-router");
const { default: Pioreactors, AssignPioreactors, PioreactorCard } = require("../Pioreactors");
const { resetDescriptorCaches } = require("../utils/jobs");

const assignmentWorkers = [
  {
    pioreactor_unit: "unit-1",
    experiment: null,
  },
  {
    pioreactor_unit: "unit-2",
    experiment: "exp1",
  },
];

function renderAssignPioreactors() {
  return render(
    <MemoryRouter>
      <AssignPioreactors experiment="exp1" />
    </MemoryRouter>,
  );
}

function renderPioreactors() {
  return render(
    <ThemeProvider theme={createTheme()}>
      <MemoryRouter>
        <Pioreactors title="Pioreactor ~ Pioreactors" />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

function createDeferred() {
  let resolve;
  const promise = new Promise((resolvePromise) => {
    resolve = resolvePromise;
  });

  return { promise, resolve };
}

function worker(pioreactorUnit) {
  return {
    pioreactor_unit: pioreactorUnit,
    is_active: 1,
    model_name: "pioreactor_40ml",
    model_version: "1.0",
  };
}

function jsonResponse(data) {
  return Promise.resolve({
    ok: true,
    json: async () => data,
  });
}

function sharedConfigResponse() {
  return Promise.resolve({
    ok: true,
    text: async () => "[leds]\nA=shared_led\n",
  });
}

describe("AssignPioreactors", () => {
  beforeEach(() => {
    mockNavigate.mockReset();
    global.fetch = jest.fn((url, options = {}) => {
      if (url === "/api/workers/assignments") {
        return Promise.resolve({
          ok: true,
          json: async () => assignmentWorkers,
        });
      }

      if (url === "/api/experiments/exp1/workers" && options.method === "PUT") {
        return Promise.resolve({
          ok: true,
          json: async () => ({}),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("closes and refreshes after successful assignment changes", async () => {
    renderAssignPioreactors();

    fireEvent.click(screen.getByRole("button", { name: /assign pioreactors/i }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /unit-1/i }));
    fireEvent.click(screen.getByRole("button", { name: "Assign 1" }));

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith(0);
    });
  });

  test("keeps the dialog open and shows an error when assignment update returns non-OK", async () => {
    global.fetch = jest.fn((url, options = {}) => {
      if (url === "/api/workers/assignments") {
        return Promise.resolve({
          ok: true,
          json: async () => assignmentWorkers,
        });
      }

      if (url === "/api/experiments/exp1/workers" && options.method === "PUT") {
        return Promise.resolve({
          ok: false,
          status: 404,
          statusText: "Not Found",
          json: async () => ({ error: "Worker assignment changed." }),
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderAssignPioreactors();

    fireEvent.click(screen.getByRole("button", { name: /assign pioreactors/i }));
    fireEvent.click(await screen.findByRole("checkbox", { name: /unit-1/i }));
    fireEvent.click(screen.getByRole("button", { name: "Assign 1" }));

    expect(
      await screen.findByText("Some Pioreactor assignments could not be updated. Please refresh and try again."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: /assign pioreactors/i })).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

describe("Pioreactors unit configuration loading", () => {
  beforeEach(() => {
    mockExperimentMetadata = { experiment: "exp1" };
    resetDescriptorCaches();
    jest.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.resetAllMocks();
  });

  test("uses one filtered bulk request while preserving unit failures and shared fallback", async () => {
    const workers = [worker("unit-1"), worker("unit-2")];

    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return sharedConfigResponse();
      }
      if (url === "/api/experiments/exp1/workers") {
        return jsonResponse(workers);
      }
      if (url === "/api/models") {
        return jsonResponse({ models: [] });
      }
      if (url === "/api/jobs/descriptors" || url === "/api/settings/descriptors") {
        return jsonResponse([]);
      }
      if (url === "/api/experiments/exp1/unit_labels") {
        return jsonResponse({});
      }
      if (url === "/api/workers/unit-1/jobs/descriptors" || url === "/api/workers/unit-2/jobs/descriptors") {
        return jsonResponse([]);
      }
      if (url === "/api/workers/unit-1/settings/descriptors" || url === "/api/workers/unit-2/settings/descriptors") {
        return jsonResponse([]);
      }
      if (url === "/api/config/units/$broadcast?unit=unit-1&unit=unit-2") {
        return jsonResponse({
          configs: {
            "unit-1": { leds: { A: "unit1_led" } },
            "extra-unit": { leds: { A: "extra_led" } },
          },
          errors: {
            "unit-2": { error: { message: "Could not reach unit-2." } },
            "extra-error": { error: { message: "Could not reach extra-error." } },
          },
        });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    renderPioreactors();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/config/units/$broadcast?unit=unit-1&unit=unit-2",
      );
    });
    expect(
      global.fetch.mock.calls.filter(([url]) => url.startsWith("/api/config/units/")),
    ).toHaveLength(1);

    expect((await screen.findAllByText("unit-1")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("unit-2")).length).toBeGreaterThan(0);
    expect(screen.queryByText("extra-unit")).not.toBeInTheDocument();
    expect(console.error).toHaveBeenCalledWith(
      "Fetching unit configuration failed for unit-2:",
      { error: { message: "Could not reach unit-2." } },
    );
    expect(console.error).not.toHaveBeenCalledWith(
      "Fetching unit configuration failed for extra-error:",
      expect.anything(),
    );
  });

  test("ignores an older bulk response after the experiment workers change", async () => {
    const oldConfigRequest = createDeferred();
    const newConfigRequest = createDeferred();

    global.fetch = jest.fn((url) => {
      if (url === "/api/config/shared") {
        return sharedConfigResponse();
      }
      if (url === "/api/experiments/exp1/workers") {
        return jsonResponse([worker("unit-1")]);
      }
      if (url === "/api/experiments/exp2/workers") {
        return jsonResponse([worker("unit-2")]);
      }
      if (url === "/api/models") {
        return jsonResponse({ models: [] });
      }
      if (url === "/api/jobs/descriptors" || url === "/api/settings/descriptors") {
        return jsonResponse([]);
      }
      if (url === "/api/experiments/exp1/unit_labels" || url === "/api/experiments/exp2/unit_labels") {
        return jsonResponse({});
      }
      if (url.endsWith("/jobs/descriptors") || url.endsWith("/settings/descriptors")) {
        return jsonResponse([]);
      }
      if (url === "/api/config/units/$broadcast?unit=unit-1") {
        return oldConfigRequest.promise;
      }
      if (url === "/api/config/units/$broadcast?unit=unit-2") {
        return newConfigRequest.promise;
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });

    const view = renderPioreactors();

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/config/units/$broadcast?unit=unit-1");
    });

    mockExperimentMetadata = { experiment: "exp2" };
    view.rerender(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <Pioreactors title="Pioreactor ~ Pioreactors" />
        </MemoryRouter>
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith("/api/config/units/$broadcast?unit=unit-2");
    });
    await act(async () => {
      newConfigRequest.resolve({
        ok: true,
        json: async () => ({ configs: { "unit-2": { leds: { A: "new_led" } } }, errors: {} }),
      });
    });

    expect((await screen.findAllByText("unit-2")).length).toBeGreaterThan(0);

    await act(async () => {
      oldConfigRequest.resolve({
        ok: true,
        json: async () => ({
          configs: { "unit-1": { leds: { A: "old_led" } } },
          errors: { "unit-1": { error: { message: "Stale unit-1 failure." } } },
        }),
      });
    });

    await waitFor(() => {
      expect((screen.getAllByText("unit-2")).length).toBeGreaterThan(0);
      expect(console.error).not.toHaveBeenCalledWith(
        "Fetching unit configuration failed for unit-1:",
        expect.anything(),
      );
    });
  });
});

describe("PioreactorCard live-update flash", () => {
  beforeEach(() => {
    resetDescriptorCaches();
    mockSubscribeToTopic.mockClear();
    mockUnsubscribeFromTopic.mockClear();
    global.fetch = jest.fn((url) => {
      if (url === "/api/workers/unit-1/jobs/descriptors") {
        return Promise.resolve({
          ok: true,
          json: async () => ([
            {
              job_name: "stirring",
              display_name: "Stirring",
              display: true,
              description: "Stirring control",
              source: "app",
              published_settings: [
                {
                  key: "target_rpm",
                  type: "numeric",
                  display: true,
                  default: 0,
                  unit: "rpm",
                  label: "Target RPM",
                },
              ],
            },
          ]),
        });
      }

      if (url === "/api/workers/unit-1/settings/descriptors") {
        return Promise.resolve({ ok: true, json: async () => [] });
      }

      throw new Error(`Unexpected fetch call: ${url}`);
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("keeps hydration and rounded repeats quiet, then flashes visible live changes", async () => {
    render(
      <ThemeProvider theme={createTheme()}>
        <MemoryRouter>
          <PioreactorCard
            unit="unit-1"
            experiment="experiment-1"
            isUnitActive={true}
            config={{ PWM: {}, leds: {} }}
            initialLabel="Unit 1"
          />
        </MemoryRouter>
      </ThemeProvider>,
    );

    await waitFor(() => {
      expect(mockSubscribeToTopic.mock.calls.some((call) => call[2] === "PioreactorCardDynamic")).toBe(true);
    });
    const dynamicSubscription = mockSubscribeToTopic.mock.calls.find(
      (call) => call[2] === "PioreactorCardDynamic",
    );
    const onMessage = dynamicSubscription[1];
    const statePillBeforeHydration = screen.getByText("Off");
    const settingPillBeforeHydration = screen.getByText("0 rpm");

    act(() => {
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/$state",
        Buffer.from("ready"),
        { retain: true },
      );
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/target_rpm",
        Buffer.from("100"),
        { retain: false },
      );
    });

    expect(screen.getByText("On")).toBe(statePillBeforeHydration);
    expect(screen.getByText("100 rpm")).toBe(settingPillBeforeHydration);

    act(() => {
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/target_rpm",
        Buffer.from("100.001"),
        { retain: false },
      );
    });
    expect(screen.getByText("100 rpm")).toBe(settingPillBeforeHydration);

    act(() => {
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/$state",
        Buffer.from("sleeping"),
        { retain: false },
      );
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/target_rpm",
        Buffer.from("101"),
        { retain: false },
      );
    });

    await waitFor(() => {
      expect(screen.getByText("Paused")).not.toBe(statePillBeforeHydration);
      expect(screen.getByText("101 rpm")).not.toBe(settingPillBeforeHydration);
    });
    const flashedStatePill = screen.getByText("Paused");
    const flashedSettingPill = screen.getByText("101 rpm");

    act(() => {
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/$state",
        Buffer.from("sleeping"),
        { retain: false },
      );
      onMessage(
        "pioreactor/unit-1/experiment-1/stirring/target_rpm",
        Buffer.from("101"),
        { retain: false },
      );
    });

    expect(screen.getByText("Paused")).toBe(flashedStatePill);
    expect(screen.getByText("101 rpm")).toBe(flashedSettingPill);
  });
});
