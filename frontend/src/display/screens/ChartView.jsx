import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDisplay } from "../context";
import { useTopicStream } from "../hooks";
import { Segmented } from "../ui";
import { computeDomain, drawChart, readChartTheme, seriesColor } from "../chartDraw";
import useExperimentChartPreferences from "../../hooks/useExperimentChartPreferences";
import { experimentPathSegment } from "../../utils/url";

const TARGET_POINTS = 600;
const LIVE_REDRAW_MS = 2000;
const CURSOR_CLEAR_MS = 6000;
const PARTITIONED_CHARTS = new Set(["raw_optical_density", "optical_density"]);
const CHART_KEY_STORAGE = "pioreactor-display-chart";
const WINDOWS = [
  { value: "default", label: "Default" },
  { value: 6, label: "6 h" },
  { value: 24, label: "24 h" },
  { value: "all", label: "All" },
];

// Chart descriptors carry small JavaScript expressions; evaluate them like the main UI does.
function evaluateLookback(expression, config) {
  if (typeof expression === "number") return expression;
  try {
    // eslint-disable-next-line no-new-func
    const value = new Function("config", `return (${expression});`)(config);
    return Number.isFinite(value) && value >= 0 ? value : 100000;
  } catch (_error) {
    return 100000;
  }
}

function evaluateTransformation(expression) {
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function(`return (${expression || "(y) => y"});`)();
    return typeof fn === "function" ? fn : (y) => y;
  } catch (_error) {
    return (y) => y;
  }
}

function parseUtc(timestamp) {
  if (typeof timestamp === "number") return timestamp;
  return Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`);
}

const toArray = (value) => (Array.isArray(value) ? value : [value]);

function readStoredChartKey() {
  try {
    return window.localStorage.getItem(CHART_KEY_STORAGE);
  } catch (_error) {
    return null;
  }
}

export default function ChartView({ unit = null }) {
  const { config, experiment, experimentMetadata, labelFor, unitColor } = useDisplay();
  const preferences = useExperimentChartPreferences({
    chartPage: unit ? "pioreactor" : "overview",
    config,
    configReady: true,
    experiment,
  });
  const charts = useMemo(() => {
    const byKey = new Map(preferences.descriptors.map((descriptor) => [descriptor.chart_key, descriptor]));
    const keys = preferences.selectedChartKeys.length ? preferences.selectedChartKeys : [...byKey.keys()];
    return keys.map((key) => byKey.get(key)).filter(Boolean);
  }, [preferences.descriptors, preferences.selectedChartKeys]);

  const [chartKey, setChartKey] = useState(readStoredChartKey);
  const [windowChoice, setWindowChoice] = useState("default");
  const chart = charts.find((candidate) => candidate.chart_key === chartKey) || charts[0];

  const chooseChart = (key) => {
    setChartKey(key);
    try {
      window.localStorage.setItem(CHART_KEY_STORAGE, key);
    } catch (_error) {
      // not critical
    }
  };

  return (
    <>
      <div className="toolbar" style={{ marginBottom: "0.5rem" }}>
        <div className="chips" style={{ flex: 1, minWidth: 0 }}>
          {charts.map((candidate) => (
            <button
              key={candidate.chart_key}
              className={`chip ${candidate === chart ? "on" : ""}`}
              onClick={() => chooseChart(candidate.chart_key)}
            >
              {candidate.title}
            </button>
          ))}
        </div>
        <Segmented options={WINDOWS} value={windowChoice} onChange={setWindowChoice} />
      </div>
      {preferences.isLoading && !chart && <div className="empty">Loading charts...</div>}
      {preferences.error && <div className="empty">{preferences.error}</div>}
      {!preferences.isLoading && !chart && !preferences.error && <div className="empty">No charts available.</div>}
      {chart && experiment && (
        <CanvasChart
          key={`${chart.chart_key}-${experiment}-${unit}-${windowChoice}`}
          chart={chart}
          unit={unit}
          experiment={experiment}
          startMs={parseUtc(experimentMetadata?.created_at || new Date().toISOString())}
          lookbackHours={
            windowChoice === "default" ? evaluateLookback(chart.lookback, config) : windowChoice === "all" ? 1000000 : windowChoice
          }
          config={config}
          labelFor={labelFor}
          unitColor={unitColor}
        />
      )}
    </>
  );
}

function CanvasChart({ chart, unit, experiment, startMs, lookbackHours, config, labelFor, unitColor }) {
  const canvasRef = useRef(null);
  const wrapRef = useRef(null);
  const seriesRef = useRef(new Map());
  const fetchedRef = useRef(false);
  const redrawTimer = useRef(null);
  const cursorTimer = useRef(null);
  const [status, setStatus] = useState("loading");
  const [names, setNames] = useState([]);
  const [hidden, setHidden] = useState(() => new Set());
  const [cursorX, setCursorX] = useState(null);
  const [version, setVersion] = useState(0);

  const partitioned = PARTITIONED_CHARTS.has(chart.chart_key);
  const transform = useMemo(() => evaluateTransformation(chart.y_transformation), [chart.y_transformation]);
  const decimals = Number.isFinite(chart.fixed_decimals) ? chart.fixed_decimals : 2;
  const xMode = config["ui.overview.settings"]?.time_display_mode === "clock" ? "clock" : "hours";
  const channelAngles = useMemo(() => config["od_config.photodiode_channel"] || {}, [config]);

  // Map a raw series name ("pio01" or "pio01-2" for photodiode channel 2) to its display entry.
  const describe = useCallback(
    (name) => {
      const match = partitioned ? name.match(/^(.*)-(\d+)$/) : null;
      if (!match) return { name, label: labelFor(name), color: unitColor(name) };
      const angle = channelAngles[match[2]];
      if (!angle || angle === "REF") return null;
      return { name, label: `${labelFor(match[1])}-${angle}°`, color: unitColor(match[1]) };
    },
    [partitioned, channelAngles, labelFor, unitColor],
  );

  const scheduleRedraw = useCallback((delay = 0) => {
    if (redrawTimer.current !== null) return;
    redrawTimer.current = setTimeout(() => {
      redrawTimer.current = null;
      setVersion((v) => v + 1);
    }, delay);
  }, []);

  useEffect(() => () => {
    clearTimeout(redrawTimer.current);
    clearTimeout(cursorTimer.current);
  }, []);

  // History
  useEffect(() => {
    const controller = new AbortController();
    const base = unit
      ? `/api/workers/${unit}/experiments/${experimentPathSegment(experiment)}/time_series/${chart.data_source}`
      : `/api/experiments/${experimentPathSegment(experiment)}/time_series/${chart.data_source}`;
    const column = chart.data_source_column ? `/${chart.data_source_column}` : "";
    fetch(`${base}${column}?target_points=${TARGET_POINTS}&lookback=${lookbackHours}`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error(`Error ${response.status}`);
        return response.json();
      })
      .then((data) => {
        const map = new Map();
        data.series.forEach((rawName, index) => {
          const entry = describe(rawName);
          if (!entry) return;
          const points = data.data[index].map((point) => ({ x: parseUtc(point.x), y: transform(point.y) }));
          map.set(rawName, { ...entry, points });
        });
        seriesRef.current = map;
        fetchedRef.current = true;
        setNames([...map.keys()].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })));
        setStatus(map.size ? "ready" : "empty");
        scheduleRedraw();
      })
      .catch((error) => {
        if (error.name === "AbortError") return;
        fetchedRef.current = true;
        setStatus("error");
      });
    return () => controller.abort();
  }, [chart, unit, experiment, lookbackHours, describe, transform, scheduleRedraw]);

  // Live points, buffered into the series and redrawn at most every few seconds.
  const topics = useMemo(
    () => toArray(chart.mqtt_topic).map((topic) => `pioreactor/${unit || "+"}/${experiment}/${topic}`),
    [chart.mqtt_topic, unit, experiment],
  );

  useTopicStream(topics, (topic, payload, packet) => {
    if (!fetchedRef.current || packet?.retain || !payload) return;
    let x;
    let y;
    try {
      if (chart.payload_key) {
        const parsed = JSON.parse(payload);
        y = Number(parsed[chart.payload_key]);
        x = parsed.timestamp ? parseUtc(parsed.timestamp) : Date.now();
      } else {
        y = Number(payload);
        x = Date.now();
      }
    } catch (_error) {
      return;
    }
    if (!Number.isFinite(y)) return;
    const parts = topic.split("/");
    const channel = parts[4].replace("raw_od", "").replace("od", "");
    const rawName = partitioned ? `${parts[1]}-${channel}` : parts[1];
    let series = seriesRef.current.get(rawName);
    if (!series) {
      const entry = describe(rawName);
      if (!entry) return;
      series = { ...entry, points: [] };
      seriesRef.current.set(rawName, series);
      setNames([...seriesRef.current.keys()].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })));
      setStatus("ready");
    }
    series.points.push({ x, y: transform(y) });
    const cutoff = Date.now() - lookbackHours * 3600000;
    if (series.points.length > TARGET_POINTS * 3) {
      // Thin old points so memory stays bounded during long sessions.
      series.points = series.points.filter((point, index) => point.x >= cutoff && (index % 2 === 0 || index > series.points.length - 50));
    }
    scheduleRedraw(document.hidden ? 60000 : LIVE_REDRAW_MS);
  });

  // Draw
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const frame = requestAnimationFrame(() => {
      const seriesList = [...seriesRef.current.values()];
      drawChart(canvas, {
        seriesList,
        hidden,
        domain: computeDomain(seriesList, hidden, chart.y_axis_domain),
        cursorX,
        theme: readChartTheme(canvas),
        xMode,
        startMs,
        decimals,
        stepped: chart.interpolation === "stepAfter",
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [version, hidden, cursorX, chart, xMode, startMs, decimals]);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(() => scheduleRedraw());
    observer.observe(wrap);
    return () => observer.disconnect();
  }, [scheduleRedraw]);

  const inspect = (event) => {
    const rect = canvasRef.current.getBoundingClientRect();
    setCursorX(event.clientX - rect.left);
    clearTimeout(cursorTimer.current);
    cursorTimer.current = setTimeout(() => setCursorX(null), CURSOR_CLEAR_MS);
  };

  const toggle = (name) =>
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  const soloOrAll = () => setHidden((previous) => (previous.size ? new Set() : previous));

  return (
    <>
      <div className="chart-wrap" ref={wrapRef}>
        <canvas
          ref={canvasRef}
          aria-label={`${chart.title} chart`}
          onPointerDown={inspect}
          onPointerMove={(event) => event.buttons && inspect(event)}
        />
        {status !== "ready" && (
          <div className="chart-status">
            {status === "loading" ? "Loading..." : status === "error" ? "Could not load data." : "No data yet."}
          </div>
        )}
      </div>
      {names.length > 1 && (
        <div className="legend">
          {hidden.size > 0 && <button onClick={soloOrAll}>Show all</button>}
          {names.map((name) => {
            const series = seriesRef.current.get(name);
            return (
              <button key={name} className={hidden.has(name) ? "off" : ""} onClick={() => toggle(name)}>
                <i style={{ background: seriesColor(series?.color) }} />
                {series?.label || name}
              </button>
            );
          })}
        </div>
      )}
      <div className="muted" style={{ fontSize: "0.75rem", marginTop: "0.3rem" }}>
        {chart.y_axis_label} · tap the chart to read values
      </div>
    </>
  );
}
