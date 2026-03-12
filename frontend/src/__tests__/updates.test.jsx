import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";

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

jest.mock("../utilities", () => ({
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
});
