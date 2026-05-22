import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: null,
    subscribeToTopic: jest.fn(),
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

const { AddNewPioreactor, WorkerCard } = require("../Inventory");

const modelsResponse = {
  models: [
    {
      model_name: "pioreactor_40ml",
      model_version: "1.5",
      display_name: "Pioreactor 40ml v1.5",
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

});

describe("WorkerCard", () => {
  beforeEach(() => {
    setupFetchMocks();
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
});
