import { useCallback, useEffect, useId, useRef, useState } from "react";
import { useMQTT } from "../providers/MQTTContext";

// Latest payload (as a string) for every topic matching the given patterns.
// Renders are batched: a burst of retained messages or readings from many
// units produces one state update per window instead of one per message.
export function useTopicValues(topics, throttleMs = 750) {
  const { subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const key = useId();
  const [values, setValues] = useState({});
  const topicKey = topics.filter(Boolean).join("\n");

  useEffect(() => {
    setValues({});
    if (!topicKey) return undefined;
    const list = topicKey.split("\n");
    const latest = {};
    let timer = null;
    let flushed = false;

    const flush = () => {
      timer = null;
      flushed = true;
      setValues({ ...latest });
    };

    const handler = (topic, message) => {
      const payload = message.toString();
      if (payload === "") {
        delete latest[topic];
      } else {
        latest[topic] = payload;
      }
      if (timer === null) timer = setTimeout(flush, flushed ? throttleMs : 80);
    };

    subscribeToTopic(list, handler, key);
    return () => {
      clearTimeout(timer);
      unsubscribeFromTopic(list, key);
    };
  }, [topicKey, subscribeToTopic, unsubscribeFromTopic, key, throttleMs]);

  return values;
}

// Calls handler(topic, payloadString, packet) for every message; no batching.
export function useTopicStream(topics, handler) {
  const { subscribeToTopic, unsubscribeFromTopic } = useMQTT();
  const key = useId();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const topicKey = topics.filter(Boolean).join("\n");

  useEffect(() => {
    if (!topicKey) return undefined;
    const list = topicKey.split("\n");
    const onMessage = (topic, message, packet) => handlerRef.current(topic, message.toString(), packet);
    subscribeToTopic(list, onMessage, key);
    return () => unsubscribeFromTopic(list, key);
  }, [topicKey, subscribeToTopic, unsubscribeFromTopic, key]);
}

export function useMqttConnected() {
  const { client } = useMQTT();
  const [connected, setConnected] = useState(Boolean(client?.connected));

  useEffect(() => {
    if (!client) {
      setConnected(false);
      return undefined;
    }
    const update = () => setConnected(Boolean(client.connected));
    update();
    client.on("connect", update);
    client.on("close", update);
    client.on("offline", update);
    return () => {
      client.off("connect", update);
      client.off("close", update);
      client.off("offline", update);
    };
  }, [client]);

  return connected;
}

// GET a JSON resource. Pass null to skip.
export function useJSON(url, { refreshMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(url) });
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    if (!url) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true }));
    fetch(url, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Error ${response.status}`);
        return response.json();
      })
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (error.name !== "AbortError") setState({ data: null, error: error.message, loading: false });
      });
    return () => controller.abort();
  }, [url, version]);

  useEffect(() => {
    if (!refreshMs || !url) return undefined;
    const timer = setInterval(reload, refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, url, reload]);

  return { ...state, reload };
}

export function useNow(intervalMs = 30000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}

// Shows a pending label after a start/stop request until MQTT reports the
// expected state, or a timeout passes. The display may lag; this gives instant feedback.
// onExpire(job, entry) is called when the expected state never arrived.
export function usePendingStates(states, { timeoutMs = 15000, onExpire } = {}) {
  const [pending, setPending] = useState({});
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  useEffect(() => {
    setPending((previous) => {
      let changed = false;
      const next = { ...previous };
      for (const [job, entry] of Object.entries(previous)) {
        if (entry.until.includes(states[job] ?? "disconnected")) {
          delete next[job];
          changed = true;
        }
      }
      return changed ? next : previous;
    });
  }, [states]);

  useEffect(() => {
    const entries = Object.values(pending);
    if (!entries.length) return undefined;
    const soonest = Math.min(...entries.map((entry) => entry.at + timeoutMs));
    const timer = setTimeout(() => {
      const now = Date.now();
      const expired = Object.entries(pending).filter(([, entry]) => entry.at + timeoutMs <= now);
      expired.forEach(([job, entry]) => onExpireRef.current?.(job, entry));
      setPending((previous) =>
        Object.fromEntries(Object.entries(previous).filter(([, entry]) => entry.at + timeoutMs > now)),
      );
    }, Math.max(0, soonest - Date.now()));
    return () => clearTimeout(timer);
  }, [pending, timeoutMs]);

  const mark = useCallback((job, label, until) => {
    setPending((previous) => ({ ...previous, [job]: { label, until, at: Date.now() } }));
  }, []);

  const clear = useCallback((job) => {
    setPending((previous) => {
      if (!(job in previous)) return previous;
      const next = { ...previous };
      delete next[job];
      return next;
    });
  }, []);

  return { pending, mark, clear };
}
