import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useKiosk } from "./context";

// Latest payload (as a string) for every topic matching the given patterns.
// Renders are batched: the burst of retained messages on subscribe produces one
// update after ~80 ms, and later messages at most one update per window.
export function useTopicValues(patterns, throttleMs = 750) {
  const { broker } = useKiosk();
  const [values, setValues] = useState({});
  const key = patterns.filter(Boolean).join("\n");

  useEffect(() => {
    setValues({});
    if (!key) return undefined;
    const latest = {};
    let timer = null;
    let flushed = false;

    const flush = () => {
      timer = null;
      flushed = true;
      setValues({ ...latest });
    };

    const unsubscribe = broker.subscribe(key.split("\n"), (topic, payload) => {
      if (payload === "") delete latest[topic];
      else latest[topic] = payload;
      if (timer === null) timer = setTimeout(flush, flushed ? throttleMs : 80);
    });
    return () => {
      clearTimeout(timer);
      unsubscribe();
    };
  }, [broker, key, throttleMs]);

  return values;
}

// Calls handler(topic, payload, packet) for every message; no batching.
export function useTopicStream(patterns, handler) {
  const { broker } = useKiosk();
  const handlerRef = useRef(handler);
  handlerRef.current = handler;
  const key = patterns.filter(Boolean).join("\n");

  useEffect(() => {
    if (!key) return undefined;
    return broker.subscribe(key.split("\n"), (...args) => handlerRef.current(...args));
  }, [broker, key]);
}

export function useBrokerConnected() {
  const { broker } = useKiosk();
  return useSyncExternalStore(broker.onStatus, broker.isConnected);
}

// Runs an async loader; pass null to skip. refreshMs > 0 reloads on an interval.
export function useAsync(loader, deps, { refreshMs = 0 } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(loader) });
  const [version, setVersion] = useState(0);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const enabled = Boolean(loader);

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, error: null, loading: false });
      return undefined;
    }
    const controller = new AbortController();
    setState((previous) => ({ ...previous, loading: true }));
    loaderRef
      .current(controller.signal)
      .then((data) => setState({ data, error: null, loading: false }))
      .catch((error) => {
        if (error.name !== "AbortError") setState((previous) => ({ data: previous.data, error: error.message, loading: false }));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, version, ...deps]);

  useEffect(() => {
    if (!refreshMs || !enabled) return undefined;
    const timer = setInterval(reload, refreshMs);
    return () => clearInterval(timer);
  }, [refreshMs, enabled, reload]);

  return { ...state, reload };
}

// Shows a pending label after a start/stop request until MQTT reports one of the
// expected states, or a timeout passes. onExpire(job, entry) is called when the
// expected state never arrived.
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
      Object.entries(pending)
        .filter(([, entry]) => entry.at + timeoutMs <= now)
        .forEach(([job, entry]) => onExpireRef.current?.(job, entry));
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
