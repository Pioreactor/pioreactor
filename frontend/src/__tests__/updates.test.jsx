import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const mockSubscribeToTopic = jest.fn();
const mockUnsubscribeFromTopic = jest.fn();
const mockMqttClient = {};
let subscribedHandler = null;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: () => ({
    client: mockMqttClient,
    subscribeToTopic: mockSubscribeToTopic,
    unsubscribeFromTopic: mockUnsubscribeFromTopic,
  }),
}));

jest.mock("../utils/config", () => ({
  getConfig: (setCallback) =>
    setCallback({
      "cluster.topology": {
        leader_hostname: "leader1",
      },
    }),
}));

jest.mock("react-showdown", () => ({
  __esModule: true,
  default: ({ markdown }) => <div>{markdown}</div>,
}));

const Updates = require("../Updates").default;

describe("Updates page", () => {
  beforeEach(() => {
    subscribedHandler = null;
    mockSubscribeToTopic.mockImplementation((_topic, handler) => {
      subscribedHandler = handler;
    });
    mockUnsubscribeFromTopic.mockReset();

    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("shows the leader version from the leader monitor MQTT topic", async () => {
    render(<Updates title="Pioreactor ~ Updates" />);

    await waitFor(() => {
      expect(mockSubscribeToTopic).toHaveBeenCalledWith(
        "pioreactor/leader1/$experiment/monitor/versions",
        expect.any(Function),
        "UpdatesPageHeader-leader-version",
      );
    });

    await act(async () => {
      subscribedHandler(
        "pioreactor/leader1/$experiment/monitor/versions",
        { toString: () => JSON.stringify({ app: "26.3.0" }) },
      );
    });

    expect(screen.getByText("26.3.0")).toBeTruthy();
  });

  test("accepts a valid dropped release archive in the update dialog", async () => {
    const user = userEvent.setup();
    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<Updates title="Pioreactor ~ Updates" />);

    await user.click(screen.getByRole("button", { name: /update from zip file/i }));
    const dropTarget = await screen.findByText(/drop a/i);

    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [new File(["zip"], "release_26.4.0.zip", { type: "application/zip" })],
      },
    });

    expect(await screen.findByText("release_26.4.0.zip")).toBeInTheDocument();
    expect(screen.queryByText(/not a valid release archive file/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update" })).toBeEnabled();
  });

  test("shows an error for an invalid dropped archive in the update dialog", async () => {
    const user = userEvent.setup();
    global.fetch = jest.fn((url) => {
      if (url === "https://api.github.com/repos/pioreactor/pioreactor/releases/latest") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ tag_name: "26.3.10" }),
        });
      }

      if (url === "https://raw.githubusercontent.com/Pioreactor/pioreactor/master/CHANGELOG.md") {
        return Promise.resolve({
          ok: true,
          text: () => Promise.resolve("# Changelog"),
        });
      }

      if (url === "/api/units") {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve([{ pioreactor_unit: "leader1" }]),
        });
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    render(<Updates title="Pioreactor ~ Updates" />);

    await user.click(screen.getByRole("button", { name: /update from zip file/i }));
    const dropTarget = await screen.findByText(/drop a/i);

    fireEvent.drop(dropTarget, {
      dataTransfer: {
        files: [new File(["zip"], "notes.zip", { type: "application/zip" })],
      },
    });

    expect(await screen.findByText(/not a valid release archive file/i)).toBeInTheDocument();
    expect(screen.queryByText("notes.zip")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Update" })).toBeDisabled();
  });
});
