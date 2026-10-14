import { useEffect, useMemo, useRef, useState } from "react";
import { enc, leaderApi } from "../api";
import { useKiosk } from "../context";
import { useTopicStream } from "../hooks";
import { Icon } from "../icons";
import { useKeyboard } from "../Keyboard";
import { Empty, Segmented, useToast } from "../ui";
import { parseLogMessage, splitTraceback } from "../../utils/logMessage";

const LEVELS = ["info", "notice", "warning", "error"];
// Where a log came from: this experiment's activities, or this unit's system
// (updates, cluster membership, the monitor), which logs under "$experiment".
const SOURCES = [
  { value: "all", label: "All" },
  { value: "experiment", label: "Experiment" },
  { value: "system", label: "System" },
];
const MAX_ROWS = 100; // each history endpoint returns at most 100 rows

function historyPath(source, unit, experiment) {
  if (source === "system") return `/units/${enc(unit)}/system_logs?min_level=info`;
  if (source === "experiment") return `/workers/${enc(unit)}/experiments/${enc(experiment)}/logs?min_level=info`;
  // This experiment and system logs together, from the last 24 hours.
  return `/workers/${enc(unit)}/experiments/${enc(experiment)}/recent_logs?min_level=info&lines=${MAX_ROWS}`;
}
const FLUSH_MS = 500;

function parseUtc(timestamp) {
  return Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`);
}

function formatTime(ms) {
  const date = new Date(ms);
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return Date.now() - ms > 20 * 3600000 ? `${date.getMonth() + 1}/${date.getDate()} ${time}` : time;
}

let liveKey = 0;

// Entity names arrive wrapped in backticks, e.g. "Assigned pioreactor `pio01`". Show them as
// inline tags instead of raw backticks. A traceback only shows when the row is expanded.
function LogText({ message, unit, experiment, expanded }) {
  const { summary, exceptionLine, traceback } = splitTraceback(message);
  const segments = parseLogMessage(summary || exceptionLine || "", { units: new Set([unit]), experiment });
  return (
    <>
      {segments.map((segment, index) =>
        segment.type === "text" ? (
          segment.text
        ) : (
          <span key={index} className={`log-entity ${segment.type}`}>
            {segment.text}
          </span>
        ),
      )}
      {summary && exceptionLine && <span className="log-exception">{exceptionLine}</span>}
      {expanded && traceback && <pre className="log-traceback">{traceback}</pre>}
    </>
  );
}

export default function Logs() {
  const { unit, experiment } = useKiosk();
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const [chosenSource, setSource] = useState("all");
  // System logs don't need an experiment; the others do.
  const source = experiment ? chosenSource : "system";
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const buffer = useRef([]);
  const timer = useRef(null);

  useEffect(() => {
    if (experiment === undefined) return undefined;
    const controller = new AbortController();
    setLogs(null);
    setError(null);
    leaderApi(historyPath(source, unit, experiment), { signal: controller.signal })
      .then((rows) =>
        setLogs(
          rows.map((row, index) => ({
            key: `h${index}-${row.timestamp}`,
            ms: parseUtc(row.timestamp),
            task: row.task,
            level: String(row.level).toLowerCase(),
            message: row.message,
          })),
        ),
      )
      .catch((err) => {
        if (err.name === "AbortError") return;
        setError(err.message);
        setLogs([]);
      });
    return () => controller.abort();
  }, [unit, experiment, source]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const topics = useMemo(() => {
    if (experiment === undefined) return [];
    const experiments = { all: [experiment, "$experiment"], experiment: [experiment], system: ["$experiment"] }[source];
    return experiments.flatMap((exp) => LEVELS.map((level) => `pioreactor/${unit}/${exp}/logs/+/${level}`));
  }, [unit, experiment, source]);

  // New entries are buffered and added in one update, so a burst doesn't re-render per line.
  useTopicStream(topics, (_topic, payload, packet) => {
    if (packet?.retain) return;
    try {
      const parsed = JSON.parse(payload);
      liveKey += 1;
      buffer.current.push({
        key: `l${liveKey}`,
        ms: parsed.timestamp ? parseUtc(parsed.timestamp) : Date.now(),
        task: parsed.task,
        level: String(parsed.level).toLowerCase(),
        message: String(parsed.message),
      });
    } catch (_error) {
      return;
    }
    if (timer.current === null) {
      timer.current = setTimeout(() => {
        timer.current = null;
        const incoming = buffer.current;
        buffer.current = [];
        setLogs((previous) => [...incoming, ...(previous || [])].sort((a, b) => b.ms - a.ms).slice(0, MAX_ROWS));
      }, FLUSH_MS);
    }
  });

  const addNote = () =>
    openKeyboard({
      label: `Note for ${unit}`,
      type: "text",
      submitLabel: "Add note",
      validate: (text) => (text.trim() ? null : "Write a note first."),
      onSubmit: async (message) => {
        try {
          await leaderApi(`/workers/${enc(unit)}/experiments/${enc(experiment)}/logs`, {
            method: "POST",
            body: { message: message.trim(), timestamp: new Date().toISOString(), task: "note", source: "UI", level: "INFO" },
          });
          toast("Note added");
        } catch (err) {
          toast.error(err);
        }
      },
    });

  return (
    <div className="content">
      {experiment && (
        <div className="toolbar">
          <Segmented label="Source" options={SOURCES} value={source} onChange={setSource} />
          <span className="grow" />
          <button type="button" className="btn" onClick={addNote}>
            <Icon name="add" />
            Add note
          </button>
        </div>
      )}
      {error && <div className="banner">Could not load earlier logs from the leader: {error}</div>}
      {logs === null && <Empty>Loading...</Empty>}
      {logs !== null && logs.length === 0 && !error && (
        <Empty>{source === "all" ? "No logs in the last 24 hours." : "No logs yet."}</Empty>
      )}
      {logs?.length > 0 && (
        <div className="list">
          {logs.map((log) => (
            <button
              type="button"
              key={log.key}
              className={`log-row ${log.level} ${expanded === log.key ? "expanded" : ""}`}
              onClick={() => setExpanded(expanded === log.key ? null : log.key)}
            >
              <span className="muted num">{formatTime(log.ms)}</span>
              <span className="task truncate">{(log.task || "").replace(/_/g, " ")}</span>
              <span className="msg">
                {log.level === "error" || log.level === "warning" ? (
                  <strong>{log.level === "error" ? "Error: " : "Warning: "}</strong>
                ) : null}
                <LogText message={log.message} unit={unit} experiment={experiment} expanded={expanded === log.key} />
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
