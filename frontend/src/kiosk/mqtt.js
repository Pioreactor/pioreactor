import mqtt from "mqtt";

// One broker connection for the whole screen. Unlike the main app's MQTTProvider,
// it never gives up: a screen can boot before the broker is ready, and the broker
// (on the leader) can restart while the screen stays on.

const RECONNECT_MS = 3000;

export function topicMatches(pattern, topic) {
  const p = pattern.split("/");
  const t = topic.split("/");
  for (let i = 0; i < p.length; i += 1) {
    if (p[i] === "#") return true;
    if (i >= t.length) return false;
    if (p[i] !== "+" && p[i] !== t[i]) return false;
  }
  return p.length === t.length;
}

export function createBroker(mqttConfig, clientName) {
  const {
    username,
    password,
    ws_protocol: protocol = "ws",
    broker_address: brokerAddress = "localhost", // may be "addr1;addr2"
    broker_ws_port: port = 9001,
  } = mqttConfig || {};

  const servers = brokerAddress
    .split(";")
    .map((host) => host.trim())
    .filter(Boolean)
    .map((host) => ({ host, port: Number(port), protocol }));

  const client = mqtt.connect({
    servers,
    protocol,
    path: "/mqtt",
    username,
    password,
    clientId: `${clientName}-${Math.random().toString(16).slice(2, 10)}`,
    keepalive: 30,
    clean: true,
    reconnectPeriod: RECONNECT_MS,
    connectTimeout: 5000,
  });

  // pattern -> Map(id -> handler)
  const subscriptions = new Map();
  // Last payload per topic, replayed to a handler that joins a pattern someone
  // else already subscribed to (the broker only sends retained messages once).
  const lastPayloads = new Map();
  const statusListeners = new Set();
  let connected = false;
  let nextId = 0;

  const setConnected = (value) => {
    if (connected === value) return;
    connected = value;
    statusListeners.forEach((listener) => listener(value));
  };

  client.on("connect", () => setConnected(true));
  client.on("close", () => setConnected(false));
  client.on("offline", () => setConnected(false));
  client.on("error", (error) => console.warn("MQTT error:", error?.message || error));

  client.on("message", (topic, message, packet) => {
    const payload = message.toString();
    if (payload === "") lastPayloads.delete(topic);
    else lastPayloads.set(topic, payload);
    for (const [pattern, handlers] of subscriptions) {
      if (!topicMatches(pattern, topic)) continue;
      for (const handler of handlers.values()) handler(topic, payload, packet);
    }
  });

  return {
    // Calls handler(topic, payloadString, packet). Returns an unsubscribe function.
    subscribe(patterns, handler) {
      const id = nextId++;
      const list = [...new Set(patterns.filter(Boolean))];
      const replay = [];
      for (const pattern of list) {
        if (!subscriptions.has(pattern)) {
          subscriptions.set(pattern, new Map());
          client.subscribe(pattern, { qos: 0 });
        } else {
          for (const [topic, payload] of lastPayloads) {
            if (topicMatches(pattern, topic)) replay.push([topic, payload]);
          }
        }
        subscriptions.get(pattern).set(id, handler);
      }
      if (replay.length) {
        queueMicrotask(() => {
          if (!subscriptions.get(list[0])?.has(id)) return;
          for (const [topic, payload] of replay) handler(topic, payload, { retain: true });
        });
      }
      return () => {
        for (const pattern of list) {
          const handlers = subscriptions.get(pattern);
          if (!handlers) continue;
          handlers.delete(id);
          if (handlers.size === 0) {
            subscriptions.delete(pattern);
            client.unsubscribe(pattern);
          }
        }
        for (const topic of lastPayloads.keys()) {
          if (![...subscriptions.keys()].some((pattern) => topicMatches(pattern, topic))) lastPayloads.delete(topic);
        }
      };
    },

    publish(topic, payload, { qos = 1, retain = false } = {}) {
      return new Promise((resolve, reject) => {
        if (!connected) {
          reject(new Error("Not connected to the leader. Try again in a moment."));
          return;
        }
        const message = typeof payload === "string" ? payload : JSON.stringify(payload);
        client.publish(topic, message, { qos, retain }, (error) => (error ? reject(error) : resolve()));
      });
    },

    isConnected: () => connected,

    onStatus(listener) {
      statusListeners.add(listener);
      return () => statusListeners.delete(listener);
    },

    end() {
      client.end(true);
    },
  };
}
