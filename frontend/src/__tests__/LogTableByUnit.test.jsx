import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { TextDecoder, TextEncoder } from "util";

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

const { MemoryRouter } = require("react-router");
const LogTableByUnit = require("../components/LogTableByUnit").default;
const LogTable = require("../components/LogTable").default;

jest.mock("../providers/MQTTContext", () => ({
  useMQTT: jest.fn(),
}));

jest.mock("../components/RecordEventLogDialog", () => () => null);

const { useMQTT } = require("../providers/MQTTContext");

describe("LogTableByUnit", () => {
  beforeEach(() => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        json: () => Promise.resolve([]),
      })
    );
  });

  afterEach(() => {
    jest.clearAllMocks();
  });

  test("re-sorts MQTT log events by timestamp after out-of-order delivery", async () => {
    const subscribeToTopic = jest.fn();
    const unsubscribeFromTopic = jest.fn();

    useMQTT.mockReturnValue({
      client: {},
      subscribeToTopic,
      unsubscribeFromTopic,
    });

    const { container } = render(
      <MemoryRouter>
        <LogTableByUnit experiment="exp1" unit="unit1" />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/workers/unit1/experiments/exp1/recent_logs?min_level=info"
      )
    );

    const onMessage = subscribeToTopic.mock.calls[0][1];

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:01.000Z",
            message: "first live event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:00.000Z",
            message: "late older event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:02.000Z",
            message: "newest live event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    const bodyRows = Array.from(container.querySelectorAll("tbody tr"));

    expect(bodyRows).toHaveLength(3);
    expect(bodyRows[0]).toHaveTextContent("newest live event");
    expect(bodyRows[1]).toHaveTextContent("first live event");
    expect(bodyRows[2]).toHaveTextContent("late older event");
    expect(screen.getByText("newest live event")).toBeInTheDocument();
  });

  test("keeps the shared experiment log table sorted after out-of-order MQTT delivery", async () => {
    const subscribeToTopic = jest.fn();
    const unsubscribeFromTopic = jest.fn();

    useMQTT.mockReturnValue({
      client: {},
      subscribeToTopic,
      unsubscribeFromTopic,
    });

    const { container } = render(
      <MemoryRouter>
        <LogTable
          units={["unit1"]}
          byDuration={false}
          experiment="exp1"
          config={{ logging: { ui_log_level: "info" } }}
          relabelMap={{}}
        />
      </MemoryRouter>
    );

    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/experiments/exp1/recent_logs?min_level=info"
      )
    );

    expect(subscribeToTopic).toHaveBeenCalledTimes(1);
    expect(subscribeToTopic).toHaveBeenCalledWith(
      [
        "pioreactor/+/exp1/logs/+/info",
        "pioreactor/+/exp1/logs/+/notice",
        "pioreactor/+/exp1/logs/+/warning",
        "pioreactor/+/exp1/logs/+/error",
        "pioreactor/+/exp1/logs/+/critical",
      ],
      expect.any(Function),
      "LogTable"
    );

    const onMessage = subscribeToTopic.mock.calls[0][1];

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:01.000Z",
            message: "first experiment event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:00.000Z",
            message: "late older experiment event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    await act(async () => {
      onMessage(
        "pioreactor/unit1/exp1/logs/app/info",
        Buffer.from(
          JSON.stringify({
            timestamp: "2026-03-23T10:00:02.000Z",
            message: "newest experiment event",
            task: "app",
            level: "info",
          })
        )
      );
    });

    const bodyRows = Array.from(container.querySelectorAll("tbody tr"));

    expect(bodyRows).toHaveLength(3);
    expect(bodyRows[0]).toHaveTextContent("newest experiment event");
    expect(bodyRows[1]).toHaveTextContent("first experiment event");
    expect(bodyRows[2]).toHaveTextContent("late older experiment event");
  });
});
