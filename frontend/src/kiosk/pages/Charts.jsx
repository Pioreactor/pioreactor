import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { enc, leaderApi } from "../api";
import { useKiosk } from "../context";
import { useAsync, useTopicStream } from "../hooks";
import { computeDomain, drawChart, readChartTheme, seriesColor } from "../chartDraw";
import { Empty, Segmented } from "../ui";
import { colors } from "../../utils/color";

// History comes from the leader's database once, when the chart opens; after
// that the chart follows live MQTT. It never polls.
const TARGET_POINTS = 600;
const LIVE_REDRAW_MS = 2000;
const HIDDEN_REDRAW_MS = 60000;
const CURSOR_CLEAR_MS = 6000;
const PARTITIONED_CHARTS = new Set(["raw_optical_density", "optical_density"]);
const CHART_KEY_STORAGE = "pioreactor-kiosk-chart";
const WINDOW_STORAGE = "pioreactor-kiosk-chart-window";
// Lookback in hours, as in the main UI's Overview. "Now" (0) loads no history and
// shows only points that arrive while the chart is open.
const ALL_TIME = 1000000;
const WINDOWS = [
  { value: ALL_TIME, label: "All" },
  { value: 24, label: "24 h" },
  { value: 6, label: "6 h" },
  { value: 0, label: "Now" },
];

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
const byName = (a, b) => a.localeCompare(b, undefined, { numeric: true });

function readStored(key) {
  try {
    return window.localStorage.getItem(key);
  } catch (_error) {
    return null;
  }
}

function store(key, value) {
  try {
    window.localStorage.setItem(key, String(value));
  } catch (_error) {
    // not critical
  }
}

// Defaults to all time, like the main UI.
function readStoredWindow() {
  const raw = readStored(WINDOW_STORAGE);
  const hours = Number(raw);
  return raw !== null && WINDOWS.some((option) => option.value === hours) ? hours : ALL_TIME;
}

// Same selection rules as the main UI's Pioreactor page.
function selectCharts(descriptors, preferences, config) {
  const available = new Map(descriptors.map((descriptor) => [descriptor.chart_key, descriptor]));
  const stored = preferences?.pioreactor_chart_keys ?? null;
  const defaults = Object.entries(config["ui.overview.charts"] || {})
    .filter(([, enabled]) => enabled === "1")
    .map(([key]) => key);
  const keys = (stored ?? defaults).filter((key) => available.has(key));
  return (keys.length ? keys : [...available.keys()]).map((key) => available.get(key));
}

export default function Charts() {
  const { config, experiment, experimentMetadata } = useKiosk();
  const resource = useAsync(
    experiment
      ? (signal) =>
          Promise.all([
            leaderApi("/charts/descriptors", { signal }),
            leaderApi(`/experiments/${enc(experiment)}/chart_preferences`, { signal }).catch(() => null),
          ])
      : null,
    [experiment],
  );
  const charts = useMemo(
    () => (resource.data ? selectCharts(resource.data[0], resource.data[1], config) : []),
    [resource.data, config],
  );

  const [chartKey, setChartKey] = useState(() => readStored(CHART_KEY_STORAGE));
  const [lookbackHours, setLookbackHours] = useState(readStoredWindow);
  const chart = charts.find((candidate) => candidate.chart_key === chartKey) || charts[0];

  if (!experiment) return <Empty>Join an experiment to see charts.</Empty>;

  return (
    <div className="content fill">
      <div className="toolbar">
        <div className="chips grow">
          {charts.map((candidate) => (
            <button
              type="button"
              key={candidate.chart_key}
              className={`chip ${candidate === chart ? "on" : ""}`}
              onClick={() => {
                setChartKey(candidate.chart_key);
                store(CHART_KEY_STORAGE, candidate.chart_key);
              }}
            >
              {candidate.title}
            </button>
          ))}
        </div>
        <Segmented
          label="Time window"
          options={WINDOWS}
          value={lookbackHours}
          onChange={(value) => {
            setLookbackHours(value);
            store(WINDOW_STORAGE, value);
          }}
        />
      </div>
      {resource.loading && !chart && <Empty>Loading charts...</Empty>}
      {resource.error && <Empty>Could not load charts from the leader: {resource.error}</Empty>}
      {!resource.loading && !resource.error && !chart && <Empty>No charts available.</Empty>}
      {chart && (
        <CanvasChart
          key={`${chart.chart_key}-${experiment}-${lookbackHours}`}
          chart={chart}
          experiment={experiment}
          startMs={parseUtc(experimentMetadata?.created_at || new Date().toISOString())}
          lookbackHours={lookbackHours}
        />
      )}
    </div>
  );
}

function CanvasChart({ chart, experiment, startMs, lookbackHours }) {
  const { unit, config } = useKiosk();
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

  // Series are "<unit>" or, for OD, "<unit>-<channel>" mapped to the sensor angle.
  // REF channels are hidden. Colours follow the series' position.
  const describe = useCallback(
    (name, index) => {
      const color = colors[index % colors.length];
      const match = partitioned ? name.match(/^(.*)-(\d+)$/) : null;
      if (!match) return { name, label: name === unit ? chart.title : name, color };
      const angle = channelAngles[match[2]];
      if (!angle || angle === "REF") return null;
      return { name, label: `${angle}° sensor`, color };
    },
    [partitioned, channelAngles, unit, chart.title],
  );

  const scheduleRedraw = useCallback((delay = 0) => {
    if (redrawTimer.current !== null) return;
    redrawTimer.current = setTimeout(() => {
      redrawTimer.current = null;
      setVersion((v) => v + 1);
    }, delay);
  }, []);

  useEffect(
    () => () => {
      clearTimeout(redrawTimer.current);
      clearTimeout(cursorTimer.current);
    },
    [],
  );

  // History, for this unit only (smaller queries than the cluster-wide endpoints).
  useEffect(() => {
    if (lookbackHours === 0) {
      fetchedRef.current = true;
      setStatus("waiting");
      return undefined;
    }
    const controller = new AbortController();
    const column = chart.data_source_column ? `/${enc(chart.data_source_column)}` : "";
    leaderApi(
      `/workers/${enc(unit)}/experiments/${enc(experiment)}/time_series/${enc(chart.data_source)}${column}?target_points=${TARGET_POINTS}&lookback=${lookbackHours}`,
      { signal: controller.signal },
    )
      .then((data) => {
        const map = new Map();
        data.series.forEach((rawName, index) => {
          const entry = describe(rawName, index);
          if (!entry) return;
          const points = data.data[index].map((point) => ({ x: parseUtc(point.x), y: transform(point.y) }));
          map.set(rawName, { ...entry, points });
        });
        seriesRef.current = map;
        fetchedRef.current = true;
        setNames([...map.keys()].sort(byName));
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
    () => toArray(chart.mqtt_topic).map((topic) => `pioreactor/${unit}/${experiment}/${topic}`),
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
      const entry = describe(rawName, seriesRef.current.size);
      if (!entry) return;
      series = { ...entry, points: [] };
      seriesRef.current.set(rawName, series);
      setNames([...seriesRef.current.keys()].sort(byName));
      setStatus("ready");
    }
    series.points.push({ x, y: transform(y) });
    if (series.points.length > TARGET_POINTS * 3) {
      // Thin old points so memory stays bounded during long sessions. "Now" keeps
      // everything since the chart opened, like the main UI.
      const cutoff = lookbackHours > 0 ? Date.now() - lookbackHours * 3600000 : -Infinity;
      const keepFrom = series.points.length - 50;
      series.points = series.points.filter((point, index) => point.x >= cutoff && (index % 2 === 0 || index > keepFrom));
    }
    scheduleRedraw(document.hidden ? HIDDEN_REDRAW_MS : LIVE_REDRAW_MS);
  });

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

  // "Tap to read" replaces hover tooltips.
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
            {
              {
                loading: "Loading...",
                error: "Could not load data from the leader.",
                waiting: "Waiting for new data...",
              }[status] || "No data yet."
            }
          </div>
        )}
      </div>
      <div className="chart-foot">
        <span className="muted">{chart.y_axis_label} · tap the chart to read values</span>
        {names.length > 1 && (
          <div className="legend">
            {names.map((name) => {
              const series = seriesRef.current.get(name);
              return (
                <button type="button" key={name} className={hidden.has(name) ? "off" : ""} onClick={() => toggle(name)}>
                  <i style={{ background: seriesColor(series?.color) }} />
                  {series?.label || name}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </>
  );
}
