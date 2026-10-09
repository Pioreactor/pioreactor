import { useEffect, useMemo, useRef, useState } from "react";
import { useDisplay } from "../context";
import Header from "../Header";
import { useTopicStream } from "../hooks";
import { Icon, Segmented, useToast } from "../ui";
import { useKeyboard } from "../Keyboard";
import { experimentPathSegment } from "../../utils/url";

const LEVELS = ["debug", "info", "notice", "warning", "error"];
const LEVEL_OPTIONS = [
  { value: "info", label: "All" },
  { value: "notice", label: "Notice+" },
  { value: "warning", label: "Warnings" },
  { value: "error", label: "Errors" },
];
const MAX_ROWS = 100; // the recent_logs API caps lines at 100

function parseUtc(timestamp) {
  return Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(timestamp) ? timestamp : `${timestamp}Z`);
}

function formatTime(ms) {
  const date = new Date(ms);
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return Date.now() - ms > 20 * 3600000 ? `${date.getMonth() + 1}/${date.getDate()} ${time}` : time;
}

export default function Logs() {
  const { experiment, units, labelFor } = useDisplay();
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const [minLevel, setMinLevel] = useState("info");
  const [unitFilter, setUnitFilter] = useState(null);
  const [logs, setLogs] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const buffer = useRef([]);
  const timer = useRef(null);

  useEffect(() => {
    if (!experiment) return undefined;
    const controller = new AbortController();
    setLogs(null);
    fetch(`/api/experiments/${experimentPathSegment(experiment)}/recent_logs?min_level=${minLevel}&lines=${MAX_ROWS}`, {
      signal: controller.signal,
    })
      .then((response) => (response.ok ? response.json() : []))
      .then((rows) =>
        setLogs(
          rows.map((row, index) => ({
            key: `h${index}-${row.timestamp}`,
            ms: parseUtc(row.timestamp),
            unit: row.pioreactor_unit,
            task: row.task,
            level: String(row.level).toLowerCase(),
            message: row.message,
          })),
        ),
      )
      .catch((error) => error.name !== "AbortError" && setLogs([]));
    return () => controller.abort();
  }, [experiment, minLevel]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const topics = useMemo(
    () => (experiment ? LEVELS.slice(LEVELS.indexOf(minLevel)).map((level) => `pioreactor/+/${experiment}/logs/+/${level}`) : []),
    [experiment, minLevel],
  );

  // New entries are buffered and added in one update, so a log burst doesn't re-render per line.
  useTopicStream(topics, (topic, payload) => {
    try {
      const parsed = JSON.parse(payload);
      buffer.current.push({
        key: `l${Date.now()}-${Math.random()}`,
        ms: parsed.timestamp ? parseUtc(parsed.timestamp) : Date.now(),
        unit: topic.split("/")[1],
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
      }, 500);
    }
  });

  const addNote = () =>
    openKeyboard({
      label: unitFilter ? `Note for ${labelFor(unitFilter)}` : "Note for all assigned Pioreactors",
      type: "text",
      submitLabel: "Add note",
      validate: (text) => (text.trim() ? null : "Write a note first."),
      onSubmit: async (message) => {
        try {
          const response = await fetch(
            `/api/workers/${unitFilter || "$broadcast"}/experiments/${experimentPathSegment(experiment)}/logs`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                message: message.trim(),
                timestamp: new Date().toISOString(),
                task: "note",
                source: "UI",
                level: "INFO",
              }),
            },
          );
          if (!response.ok) throw new Error("Failed to add the note.");
          toast("Note added");
        } catch (error) {
          toast.error(error);
        }
      },
    });

  const visible = (logs || []).filter((log) => !unitFilter || log.unit === unitFilter);
  const sortedUnits = [...(units || [])].map((u) => u.pioreactor_unit).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));

  return (
    <>
      <Header
        title="Logs"
        actions={
          <button className="btn" onClick={addNote} disabled={!experiment}>
            <Icon name="add" />
            Add note
          </button>
        }
      />
      <div className="content">
        <div className="toolbar">
          <div className="chips" style={{ flex: 1, minWidth: 0 }}>
            <button className={`chip ${unitFilter ? "" : "on"}`} onClick={() => setUnitFilter(null)}>
              All Pioreactors
            </button>
            {sortedUnits.map((unit) => (
              <button key={unit} className={`chip ${unitFilter === unit ? "on" : ""}`} onClick={() => setUnitFilter(unit)}>
                {labelFor(unit)}
              </button>
            ))}
          </div>
          <Segmented options={LEVEL_OPTIONS} value={minLevel} onChange={setMinLevel} />
        </div>
        {logs === null && <div className="empty">Loading...</div>}
        {logs !== null && visible.length === 0 && <div className="empty">No logs in the last 24 hours.</div>}
        {visible.length > 0 && (
          <div className="list">
            {visible.map((log) => (
              <button
                key={log.key}
                className={`log-row ${log.level} ${expanded === log.key ? "expanded" : ""}`}
                onClick={() => setExpanded(expanded === log.key ? null : log.key)}
              >
                <span className="muted num">{formatTime(log.ms)}</span>
                <span className="truncate">
                  {labelFor(log.unit)}
                  <span className="task truncate">{(log.task || "").replace(/_/g, " ")}</span>
                </span>
                <span className="msg">
                  {log.level === "error" || log.level === "warning" ? <strong>{log.level === "error" ? "Error: " : "Warning: "}</strong> : null}
                  {log.message}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
