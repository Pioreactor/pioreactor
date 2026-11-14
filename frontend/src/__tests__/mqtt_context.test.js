import { EventEmitter } from "events";
import React, { act, useEffect } from "react";
import { render } from "@testing-library/react";
import { MQTTProvider, useMQTT, getMqttEndpoint } from "../providers/MQTTContext";
import mqtt from "mqtt";

const createMockClient = () => Object.assign(new EventEmitter(), {
  end: jest.fn(),
  subscribe: jest.fn(),
  unsubscribe: jest.fn(),
});

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
    ui_use_proxy: "false",
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

 describe("MQTT connection lifecycle", () => {
  beforeEach(() => { mqtt.connect.mockReset(); jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  test("accepts a slow initial connection and recovers repeatedly on the same client", async () => {
    const client = createMockClient();
    mqtt.connect.mockReturnValue(client);
    const view = render(<MQTTProvider name="test" config={baseConfig}><Subscriber experiment="exp" /></MQTTProvider>);
    await act(async () => { jest.advanceTimersByTime(5200); client.emit("connect"); });
    expect(client.end).not.toHaveBeenCalled();
    expect(client.subscribe).toHaveBeenCalledWith(TOPICS_FOR("exp"), { qos: 0 });
    for (let i = 0; i < 4; i++) {
      await act(async () => { client.emit("close"); client.emit("error", new Error("offline")); jest.advanceTimersByTime(15000); client.emit("connect"); });
    }
    expect(mqtt.connect).toHaveBeenCalledTimes(1);
    expect(client.end).not.toHaveBeenCalled();
    view.unmount();
    expect(client.end).toHaveBeenCalledWith(true);
  });

  test("replaces a pending client on config changes and ignores its late connection", async () => {
    const first = createMockClient(); const second = createMockClient();
    mqtt.connect.mockReturnValueOnce(first).mockReturnValueOnce(second);
    const view = render(<MQTTProvider name="test" config={baseConfig}><Subscriber experiment="exp" /></MQTTProvider>);
    view.rerender(<MQTTProvider name="test" config={{mqtt: {...baseConfig.mqtt, broker_address: "other; fallback"}}}><Subscriber experiment="exp" /></MQTTProvider>);
    expect(first.end).toHaveBeenCalledWith(true);
    await act(async () => { first.emit("connect"); });
    expect(first.subscribe).not.toHaveBeenCalled();
    expect(mqtt.connect.mock.calls[1][0]).toMatchObject({ servers: [{host: "other", port: 9001, protocol: "ws"}, {host: "fallback", port: 9001, protocol: "ws"}], connectTimeout: 10000, reconnectPeriod: 5000 });
    view.unmount();
    expect(second.end).toHaveBeenCalledWith(true);
  });

  test.each([4, 5, 134, 135])("stops retrying authentication rejection %s", async code => {
    const client = createMockClient(); mqtt.connect.mockReturnValue(client);
    const view = render(<MQTTProvider name="test" config={baseConfig} />);
    await act(async () => { client.emit("error", Object.assign(new Error("denied"), {code})); });
    expect(client.end).toHaveBeenCalledWith(true);
    view.unmount();
  });
 });

test.each([
  ['http://192.168.0.36:8080', '192.168.0.36', 8080, 'ws'],
  ['https://leader.example.org', 'leader.example.org', 443, 'wss'],
  ['http://leader.local', 'leader.local', 80, 'ws'],
])('uses page origin %s by default', (url, host, port, protocol) => {
  expect(getMqttEndpoint({broker_address: 'unresolvable.local'}, new URL(url))).toEqual({servers: [{host, port, protocol}], protocol});
});
