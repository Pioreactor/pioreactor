import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

let mockMQTTClient = {};
const mockSubscribeToTopic = jest.fn();

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: mockMQTTClient,
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: jest.fn(),
  }),
}));

jest.mock("../providers/ExperimentContext", () => ({
  useExperiment: () => ({
    selectExperiment: jest.fn(),
  }),
}));

jest.mock("material-ui-confirm", () => ({
  useConfirm: () => jest.fn(() => Promise.resolve()),
}));

jest.mock("react-router", () => ({
  Link: ({ children, to: _to, ...props }) => <a {...props}>{children}</a>,
  useNavigate: () => jest.fn(),
}));

const { AddNewPioreactor, Blink, WorkerCard, default: Inventory } = require("../Inventory");
const { resetDescriptorCaches } = require("../utils/jobs");

const modelsResponse = {
  models: [
    {
      model_name: "pioreactor_40ml",
      model_version: "1.5",
      display_name: "Pioreactor 40ml v1.5",
      reactor_capacity_ml: 40,
      is_contrib: false,
      is_legacy: false,
    },
  ],
};

function renderAddNewPioreactor() {
  const setWorkers = jest.fn();
  render(<AddNewPioreactor setWorkers={setWorkers} />);
  return { setWorkers };
}

function setupFetchMocks() {
  global.fetch = jest.fn((url) => {
    if (url === "/api/models") {
      return Promise.resolve({
        ok: true,
        json: async () => modelsResponse,
      });
    }

    if (url === "/api/workers/discover") {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      });
    }

    if (url === "/api/workers/setup") {
      return Promise.resolve({
        ok: true,
        json: async () => ({ msg: "ok" }),
      });
    }

    if (url === "/api/jobs/descriptors") {
      return Promise.resolve({
        ok: true,
        json: async () => [],
      });
    }

    if (url === "/api/workers/unit1/experiment") {
      return Promise.resolve({
        ok: false,
        json: async () => ({}),
      });
    }

    throw new Error(`Unexpected fetch: ${url}`);
  });
}

function getSetupRequestBody() {
  const setupCall = global.fetch.mock.calls.find(([url]) => url === "/api/workers/setup");
  return JSON.parse(setupCall[1].body);
}

function setupInventoryFetchMocks({failedEndpoint = null} = {}) {
  const workers = [
    {
      pioreactor_unit: "unit1",
      is_active: true,
      model_name: "pioreactor_40ml",
      model_version: "1.5",
      ipv4_address: "192.168.1.10",
    },
    {
      pioreactor_unit: "unit2",
      is_active: true,
      model_name: "pioreactor_40ml",
      model_version: "1.5",
      ipv4_address: "192.168.1.11",
    },
  ];

  global.fetch = jest.fn((url, options = {}) => {
    if (url === "/api/workers") {
      return Promise.resolve({ ok: true, json: async () => workers });
    }
    if (url === "/api/models") {
      if (failedEndpoint === url) {
        return Promise.resolve({ ok: false, statusText: "Unavailable" });
      }
      return Promise.resolve({ ok: true, json: async () => modelsResponse });
    }
    if (url === "/api/workers/assignments") {
      if (failedEndpoint === url) {
        return Promise.resolve({ ok: false, statusText: "Unavailable" });
      }
      return Promise.resolve({
        ok: true,
        json: async () => [
          { pioreactor_unit: "unit1", experiment: "experiment-a", is_active: 1 },
          { pioreactor_unit: "unit2", experiment: null, is_active: 1 },
        ],
      });
    }
    if (url === "/api/config/shared") {
      return Promise.resolve({ ok: true, text: async () => "[cluster.topology]\nleader_hostname=leader\n" });
    }
    if (url === "/api/jobs/descriptors") {
      return Promise.resolve({ ok: true, json: async () => [] });
    }
    if (url === "/api/experiments/experiment-a/workers/unit1" && options.method === "DELETE") {
      return Promise.resolve({ ok: true });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  });
}

describe("Inventory bootstrap", () => {
  beforeEach(() => {
    mockMQTTClient = null;
    mockSubscribeToTopic.mockReset();
    resetDescriptorCaches();
    setupInventoryFetchMocks();
  });

  afterEach(() => {
    mockMQTTClient = {};
    jest.restoreAllMocks();
  });

  test("loads models and assignments once for multiple workers without MQTT", async () => {
    render(<Inventory title="Inventory" />);

    expect(await screen.findByText("experiment-a")).toBeInTheDocument();
    expect(screen.getAllByText("Pioreactor 40ml v1.5")).toHaveLength(2);
    expect(screen.getAllByText("40")).toHaveLength(2);

    const requestedUrls = global.fetch.mock.calls.map(([url]) => url);
    expect(requestedUrls.filter((url) => url === "/api/models")).toHaveLength(1);
    expect(requestedUrls.filter((url) => url === "/api/workers/assignments")).toHaveLength(1);
    expect(requestedUrls.some((url) => /\/api\/workers\/[^/]+\/experiment$/.test(url))).toBe(false);
    expect(mockSubscribeToTopic).not.toHaveBeenCalled();
  });

  test.each([
    ["models", "/api/models", "experiment-a"],
    ["assignments", "/api/workers/assignments", "Pioreactor 40ml v1.5"],
  ])("keeps workers and successful %s data when one bootstrap request fails", async (_name, failedEndpoint, successfulText) => {
    jest.spyOn(console, "error").mockImplementation(() => {});
    setupInventoryFetchMocks({failedEndpoint});

    render(<Inventory title="Inventory" />);

    expect(await screen.findByText("unit1")).toBeInTheDocument();
    expect(screen.getByText("unit2")).toBeInTheDocument();
    expect(await screen.findAllByText(successfulText)).not.toHaveLength(0);
  });

  test("updates the affected card after unassigning without a page reload", async () => {
    render(<Inventory title="Inventory" />);

    expect(await screen.findByText("experiment-a")).toBeInTheDocument();
    const unassignButtons = screen.getAllByRole("button", {name: "Unassign"});
    fireEvent.click(unassignButtons[0]);

    await waitFor(() => expect(screen.queryByText("experiment-a")).not.toBeInTheDocument());
    expect(screen.getAllByText("Unassigned")).toHaveLength(2);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/experiments/experiment-a/workers/unit1",
      {method: "DELETE"},
    );
  });
});

describe("AddNewPioreactor", () => {
  beforeEach(() => {
    setupFetchMocks();
  });

  test("submits the optional IPv4 address when provided", async () => {
    renderAddNewPioreactor();

    fireEvent.click(screen.getByRole("button", { name: /^add new pioreactor$/i }));
    fireEvent.change(await screen.findByRole("textbox", { name: /hostname/i }), { target: { value: "new-unit" } });
    fireEvent.change(screen.getByRole("textbox", { name: /ipv4 address/i }), { target: { value: "192.168.1.22" } });
    fireEvent.click(screen.getByRole("button", { name: /^add pioreactor$/i }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/workers/setup", expect.any(Object)));
    expect(getSetupRequestBody()).toMatchObject({
      name: "new-unit",
      model: "pioreactor_40ml",
      version: "1.5",
      ipv4_address: "192.168.1.22",
    });
  });

  test("omits IPv4 address when blank", async () => {
    renderAddNewPioreactor();

    fireEvent.click(screen.getByRole("button", { name: /^add new pioreactor$/i }));
    fireEvent.change(await screen.findByRole("textbox", { name: /hostname/i }), { target: { value: "new-unit" } });
    fireEvent.click(screen.getByRole("button", { name: /^add pioreactor$/i }));

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith("/api/workers/setup", expect.any(Object)));
    expect(getSetupRequestBody()).toEqual({
      name: "new-unit",
      model: "pioreactor_40ml",
      version: "1.5",
    });
  });

  test("rejects invalid IPv4 input before submitting", async () => {
    renderAddNewPioreactor();

    fireEvent.click(screen.getByRole("button", { name: /^add new pioreactor$/i }));
    fireEvent.change(await screen.findByRole("textbox", { name: /hostname/i }), { target: { value: "new-unit" } });
    fireEvent.change(screen.getByRole("textbox", { name: /ipv4 address/i }), { target: { value: "999.168.1.22" } });
    fireEvent.click(screen.getByRole("button", { name: /^add pioreactor$/i }));

    await screen.findByText("Provide a valid IPv4 address, or leave the IPv4 field blank.");
    expect(global.fetch.mock.calls.some(([url]) => url === "/api/workers/setup")).toBe(false);
  });

  test("shows setup failure cause and remediation from backend", async () => {
    global.fetch.mockImplementation((url) => {
      if (url === "/api/models") {
        return Promise.resolve({
          ok: true,
          json: async () => modelsResponse,
        });
      }

      if (url === "/api/workers/discover") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      if (url === "/api/workers/setup") {
        return Promise.resolve({
          ok: false,
          json: async () => ({
            error: "Failed to add worker new-unit.",
            cause: "ssh connection refused",
            remediation: "Check the Pioreactor logs for the full worker setup command output.",
          }),
        });
      }

      if (url === "/api/jobs/descriptors") {
        return Promise.resolve({
          ok: true,
          json: async () => [],
        });
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });
    renderAddNewPioreactor();

    fireEvent.click(screen.getByRole("button", { name: /^add new pioreactor$/i }));
    fireEvent.change(await screen.findByRole("textbox", { name: /hostname/i }), { target: { value: "new-unit" } });
    fireEvent.click(screen.getByRole("button", { name: /^add pioreactor$/i }));

    await screen.findByText(
      "Unable to complete connection. Failed to add worker new-unit. Cause: ssh connection refused Remediation: Check the Pioreactor logs for the full worker setup command output.",
    );
  });

});

describe("WorkerCard", () => {
  beforeEach(() => {
    setupFetchMocks();
    mockSubscribeToTopic.mockReset();
  });

  test("renders backend-provided IPv4 before MQTT data arrives", async () => {
    render(
      <WorkerCard
        worker={{
          pioreactor_unit: "unit1",
          is_active: true,
          model_name: "pioreactor_40ml",
          model_version: "1.5",
          ipv4_address: "192.168.1.10",
        }}
        config={{ "cluster.topology": { leader_hostname: "leader" } }}
        leaderVersion={null}
      />,
    );

    await screen.findByText("192.168.1.10");
  });

  test("does not fetch its assignment when MQTT is connected", async () => {
    render(
      <WorkerCard
        worker={{
          pioreactor_unit: "unit1",
          is_active: true,
          model_name: "pioreactor_40ml",
          model_version: "1.5",
          ipv4_address: "192.168.1.10",
        }}
        config={{ "cluster.topology": { leader_hostname: "leader" } }}
        leaderVersion={null}
        availableModels={modelsResponse.models}
        experimentAssigned="experiment-a"
      />,
    );

    expect(await screen.findByText("experiment-a")).toBeInTheDocument();
    expect(global.fetch.mock.calls.some(([url]) => url === "/api/workers/unit1/experiment")).toBe(false);
  });

  test("shows an inline error when no model is selected", async () => {
    render(
      <WorkerCard
        worker={{
          pioreactor_unit: "unit1",
          is_active: true,
          model_name: null,
          model_version: null,
          ipv4_address: "192.168.1.10",
        }}
        config={{ "cluster.topology": { leader_hostname: "leader" } }}
        leaderVersion={null}
      />,
    );

    await screen.findByText("No model selected");
    expect(screen.queryByText("Select a Pioreactor model.")).not.toBeInTheDocument();
  });

  test("distinguishes inactive units from active units that are offline", async () => {
    mockSubscribeToTopic.mockImplementation((_topic, onMessage) => {
      onMessage("pioreactor/unit1/$experiment/monitor/$state", "disconnected");
    });

    render(
      <WorkerCard
        worker={{
          pioreactor_unit: "unit1",
          is_active: false,
          model_name: "pioreactor_40ml",
          model_version: "1.5",
          ipv4_address: "192.168.1.10",
        }}
        config={{ "cluster.topology": { leader_hostname: "leader" } }}
        leaderVersion={null}
      />,
    );

    expect(await screen.findByLabelText("Inactive, change status in Inventory")).toBeInTheDocument();

    mockSubscribeToTopic.mockImplementation((_topic, onMessage) => {
      onMessage("pioreactor/unit2/$experiment/monitor/$state", "disconnected");
    });
    render(
      <WorkerCard
        worker={{
          pioreactor_unit: "unit2",
          is_active: true,
          model_name: "pioreactor_40ml",
          model_version: "1.5",
          ipv4_address: "192.168.1.11",
        }}
        config={{ "cluster.topology": { leader_hostname: "leader" } }}
        leaderVersion={null}
      />,
    );

    expect(await screen.findByLabelText("Offline")).toBeInTheDocument();
  });
});

describe("Blink", () => {
  let animationFrameCallback;
  let originalRequestAnimationFrame;

  beforeEach(() => {
    global.fetch = jest.fn();
    originalRequestAnimationFrame = global.requestAnimationFrame;
    global.requestAnimationFrame = jest.fn((callback) => {
      animationFrameCallback = callback;
      return 1;
    });
  });

  afterEach(() => {
    global.requestAnimationFrame = originalRequestAnimationFrame;
    jest.resetAllMocks();
  });

  test("restarts the feedback animation after every completed blink", () => {
    render(<Blink unit="unit1" />);
    const button = screen.getByRole("button", { name: /identify/i });

    fireEvent.click(button);
    expect(global.fetch).toHaveBeenCalledWith("/api/workers/unit1/blink", { method: "POST" });
    expect(global.requestAnimationFrame).toHaveBeenCalledTimes(1);

    act(() => {
      animationFrameCallback();
    });
    expect(button).toHaveClass("blinkled");

    fireEvent.animationEnd(button);
    expect(button).not.toHaveClass("blinkled");

    fireEvent.click(button);
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.requestAnimationFrame).toHaveBeenCalledTimes(2);

    act(() => {
      animationFrameCallback();
    });
    expect(button).toHaveClass("blinkled");
  });
});
