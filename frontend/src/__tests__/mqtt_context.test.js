import React, { act, useEffect } from "react";
import { render } from "@testing-library/react";
import { MQTTProvider, useMQTT } from "../providers/MQTTContext";
import mqtt from "mqtt";

const createMockClient = () => {
  const handlers = {};
  return {
    once: jest.fn((event, cb) => {
      handlers[event] = cb;
    }),
    on: jest.fn((event, cb) => {
      handlers[event] = cb;
    }),
    end: jest.fn(),
    subscribe: jest.fn(),
    unsubscribe: jest.fn(),
    emit: (event, ...args) => {
      if (handlers[event]) {
        const handler = handlers[event];
        delete handlers[event];
        handler(...args);
      }
    },
  };
};

jest.mock("mqtt", () => {
  const connect = jest.fn();
  return {
    __esModule: true,
    default: { connect },
    connect,
  };
});

const TOPICS_FOR = (experiment) => [
  `pioreactor/+/${experiment}/logs/+/error`,
  `pioreactor/+/${experiment}/logs/+/warning`,
];

const Subscriber = ({ experiment }) => {
  const { client, subscribeToTopic, unsubscribeFromTopic } = useMQTT();

  useEffect(() => {
    if (!client || !experiment) {
      return undefined;
    }
    const topics = TOPICS_FOR(experiment);
    subscribeToTopic(topics, () => {}, "Subscriber");
    return () => {
      unsubscribeFromTopic(topics, "Subscriber");
    };
  }, [client, experiment, subscribeToTopic, unsubscribeFromTopic]);

  return null;
};

const baseConfig = {
  mqtt: {
    broker_address: "localhost",
    ws_protocol: "ws",
    broker_ws_port: 9001,
  },
};

const flushPromises = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("MQTTContext", () => {
  beforeEach(() => {
    mqtt.connect.mockReset();
  });

  test("unsubscribes old topics when experiment changes", async () => {
    const mockClient = createMockClient();
    mqtt.connect.mockImplementation(() => mockClient);

    let rerender;
    await act(async () => {
      ({ rerender } = render(
        <MQTTProvider name="test" config={baseConfig}>
          <Subscriber experiment="exp_a" />
        </MQTTProvider>
      ));
    });

    await act(async () => {
      await flushPromises();
      mockClient.emit("connect");
      await flushPromises();
    });

    expect(mockClient.subscribe).toHaveBeenCalledWith(TOPICS_FOR("exp_a"), { qos: 0 });

    await act(async () => {
      rerender(
        <MQTTProvider name="test" config={baseConfig}>
          <Subscriber experiment="exp_b" />
        </MQTTProvider>
      );
      await flushPromises();
    });

    expect(mockClient.unsubscribe).toHaveBeenCalledWith(TOPICS_FOR("exp_a"));
    expect(mockClient.subscribe).toHaveBeenCalledWith(TOPICS_FOR("exp_b"), { qos: 0 });
  });
});
