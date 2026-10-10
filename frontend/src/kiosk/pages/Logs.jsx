import { useEffect, useMemo, useRef, useState } from "react";
import { enc, leaderApi } from "../api";
import { useKiosk } from "../context";
import { useTopicStream } from "../hooks";
import { Icon } from "../icons";
import { useKeyboard } from "../Keyboard";
import { Empty, Segmented, useToast } from "../ui";

const LEVELS = ["debug", "info", "notice", "warning", "error"];
const LEVEL_OPTIONS = [
  { value: "info", label: "All" },
  { value: "notice", label: "Notice+" },
  { value: "warning", label: "Warnings" },
  { value: "error", label: "Errors" },
];
const MAX_ROWS = 100; // recent_logs caps lines at 100 and covers the last 24 hours
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

export default function Logs() {
  const { unit, experiment } = useKiosk();
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const [minLevel, setMinLevel] = useState("info");
  const [logs, setLogs] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const buffer = useRef([]);
  const timer = useRef(null);

  useEffect(() => {
    if (!experiment) return undefined;
    const controller = new AbortController();
    setLogs(null);
    setError(null);
    leaderApi(`/workers/${enc(unit)}/experiments/${enc(experiment)}/recent_logs?min_level=${minLevel}&lines=${MAX_ROWS}`, {
      signal: controller.signal,
    })
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
  }, [unit, experiment, minLevel]);

  useEffect(() => () => clearTimeout(timer.current), []);

  // This unit's logs for the experiment, plus its experiment-independent logs.
  const topics = useMemo(() => {
    if (!experiment) return [];
    const levels = LEVELS.slice(LEVELS.indexOf(minLevel));
    return [experiment, "$experiment"].flatMap((exp) => levels.map((level) => `pioreactor/${unit}/${exp}/logs/+/${level}`));
  }, [unit, experiment, minLevel]);

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

  if (!experiment) return <Empty>Join an experiment to see its logs.</Empty>;

  return (
    <div className="content">
      <div className="toolbar">
        <Segmented label="Minimum level" options={LEVEL_OPTIONS} value={minLevel} onChange={setMinLevel} />
        <span className="grow" />
        <button type="button" className="btn" onClick={addNote}>
          <Icon name="add" />
          Add note
        </button>
      </div>
      {error && <div className="banner">Could not load earlier logs from the leader: {error}</div>}
      {logs === null && <Empty>Loading...</Empty>}
      {logs !== null && logs.length === 0 && !error && <Empty>No logs in the last 24 hours.</Empty>}
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
                {log.message}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
