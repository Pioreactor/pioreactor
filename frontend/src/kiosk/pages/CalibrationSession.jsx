import { useCallback, useEffect, useRef, useState } from "react";
import { enc, unitApi } from "../api";
import { Icon } from "../icons";
import { EditField, useKeyboard } from "../Keyboard";
import { AsyncButton, Empty, Segmented, useConfirm, useToast } from "../ui";
import XYChart from "../XYChart";

// Runs a calibration session on this unit, one step at a time. Sessions are
// unit-local (/unit_api/calibrations/sessions), so they work without the leader.
// The step format is shared with the main UI's CalibrationSessionDialog.

const SESSION_KEY = "pioreactor-kiosk-calibration-session";

export function readStoredSession() {
  try {
    return window.localStorage.getItem(SESSION_KEY);
  } catch (_error) {
    return null;
  }
}

function storeSession(sessionId) {
  try {
    if (sessionId) window.localStorage.setItem(SESSION_KEY, sessionId);
    else window.localStorage.removeItem(SESSION_KEY);
  } catch (_error) {
    // Resuming after a reload is a convenience.
  }
}

function isHidden(step, field) {
  return field.field_type === "bool" && (field.name === "confirmed" || (step.step_type === "action" && field.name === "confirm"));
}

function initialValues(step) {
  const values = {};
  for (const field of step?.fields || []) {
    if (field.field_type === "float_list") {
      values[field.name] = Array.isArray(field.default) ? field.default : [];
    } else if (field.field_type === "bool") {
      const value = typeof field.default === "string" ? field.default.toLowerCase() === "yes" : Boolean(field.default);
      values[field.name] = value ? "yes" : "no";
    } else {
      values[field.name] = field.default ?? "";
    }
  }
  return values;
}

function formatInputs(step, values) {
  const inputs = {};
  for (const field of step?.fields || []) {
    const raw = values[field.name];
    if (field.field_type === "bool") {
      inputs[field.name] = field.name === "confirmed" ? true : raw === "yes" || raw === true;
    } else if (field.field_type === "float_list") {
      inputs[field.name] = Array.isArray(raw) ? raw : [];
    } else if (field.field_type === "float" || field.field_type === "int") {
      inputs[field.name] = raw === "" ? raw : Number(raw);
    } else {
      inputs[field.name] = raw;
    }
  }
  if (step?.step_type === "action") inputs.confirm = true;
  return inputs;
}

function missingFields(step, values) {
  return (step?.fields || []).filter((field) => {
    if (!field.required || isHidden(step, field)) return false;
    const value = values[field.name];
    return field.field_type === "float_list" ? !value?.length : value === "" || value === null || value === undefined;
  });
}

function FloatListField({ field, value, onChange }) {
  const openKeyboard = useKeyboard();
  const list = Array.isArray(value) ? value : [];

  const add = () =>
    openKeyboard({
      label: field.label,
      type: "number",
      value: "",
      hint: field.help_text,
      min: field.minimum ?? undefined,
      max: field.maximum ?? undefined,
      minError: field.min_error_msg,
      maxError: field.max_error_msg,
      submitLabel: "Add",
      onSubmit: (text) => onChange([...list, Number(text)]),
    });

  return (
    <div className="float-list">
      <div className="field-label">{field.label}</div>
      <div className="chips wrap">
        {list.map((item, index) => (
          <button
            type="button"
            key={`${item}-${index}`}
            className="chip"
            aria-label={`Remove ${item}`}
            onClick={() => onChange(list.filter((_, i) => i !== index))}
          >
            {item} <Icon name="close" />
          </button>
        ))}
        <button type="button" className="chip on" onClick={add}>
          <Icon name="add" /> Add value
        </button>
      </div>
      {field.help_text && <div className="sub">{field.help_text}</div>}
    </div>
  );
}

function StepField({ step, field, value, onChange }) {
  if (isHidden(step, field)) return null;

  if (field.field_type === "bool") {
    const options = field.options?.length ? field.options : ["yes", "no"];
    return (
      <div>
        <div className="field-label">{field.label}</div>
        <Segmented label={field.label} options={options.map((o) => ({ value: o, label: o }))} value={value} onChange={onChange} />
      </div>
    );
  }
  if (field.field_type === "choice") {
    return (
      <div>
        <div className="field-label">{field.label}</div>
        <div className="chips wrap">
          {(field.options || []).map((option) => (
            <button type="button" key={option} className={`chip ${option === value ? "on" : ""}`} onClick={() => onChange(option)}>
              {option}
            </button>
          ))}
        </div>
      </div>
    );
  }
  if (field.field_type === "float_list") {
    return <FloatListField field={field} value={value} onChange={onChange} />;
  }

  const numeric = field.field_type === "float" || field.field_type === "int";
  return (
    <EditField
      className="wide"
      label={field.label}
      value={value === "" ? null : value}
      type={numeric ? "number" : "text"}
      integer={field.field_type === "int"}
      min={field.minimum ?? undefined}
      max={field.maximum ?? undefined}
      minError={field.min_error_msg}
      maxError={field.max_error_msg}
      hint={field.help_text}
      placeholder={field.required ? "Required" : "Optional"}
      onCommit={onChange}
    />
  );
}

function StepTable({ table }) {
  const columns = Array.isArray(table.columns) ? table.columns : [];
  const rows = Array.isArray(table.rows) ? table.rows : [];
  return (
    <div>
      {table.title && <div className="field-label">{table.title}</div>}
      {rows.length === 0 ? (
        <div className="sub">{table.empty_message || "No entries yet."}</div>
      ) : (
        <table className="data-table">
          {columns.length > 0 && (
            <thead>
              <tr>
                {columns.map((column, index) => (
                  <th key={`${column}-${index}`}>{column}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {(Array.isArray(row) ? row : Object.values(row || {})).map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function resultNames(result) {
  if (!result) return [];
  if (Array.isArray(result.calibrations)) return result.calibrations.map((c) => c.calibration_name);
  const names = [];
  if (result.calibration?.calibration_name) names.push(result.calibration.calibration_name);
  if (result.estimator_name) names.push(result.estimator_name);
  return names;
}

export default function CalibrationSession({ protocol, sessionId: resumeId, onClose }) {
  const confirm = useConfirm();
  const toast = useToast();
  const [sessionId, setSessionId] = useState(resumeId || null);
  const [step, setStep] = useState(null);
  const [values, setValues] = useState({});
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(null);
  const [title, setTitle] = useState(protocol?.title || "Calibration");
  const started = useRef(false);

  const apply = useCallback((payload) => {
    setStep(payload.step);
    setValues(initialValues(payload.step));
    const session = payload.session;
    if (session) {
      setSessionId(session.session_id);
      storeSession(session.status === "in_progress" ? session.session_id : null);
      if (session.status === "failed" || session.status === "aborted") setError(session.error || "The calibration stopped.");
    }
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const request = resumeId
      ? unitApi(`/calibrations/sessions/${enc(resumeId)}`)
      : unitApi("/calibrations/sessions", {
          method: "POST",
          body: { target_device: protocol.target_device, protocol_name: protocol.protocol_name },
        });
    request
      .then((payload) => {
        if (resumeId && payload.session) setTitle(payload.session.target_device.replace(/_/g, " ") + " calibration");
        apply(payload);
      })
      .catch((err) => {
        if (resumeId) storeSession(null);
        setError(err.message);
      })
      .finally(() => setBusy(false));
  }, [apply, protocol, resumeId]);

  const advance = async (inputs) => {
    setBusy(true);
    setError(null);
    try {
      apply(await unitApi(`/calibrations/sessions/${enc(sessionId)}/inputs`, { method: "POST", body: { inputs } }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const abort = async () => {
    if (!sessionId) {
      onClose(false);
      return;
    }
    const ok = await confirm({
      title: "Abort this calibration?",
      message: "Progress in this calibration is lost. Saved calibrations are not affected.",
      confirmText: "Abort",
      danger: true,
    });
    if (!ok) return;
    try {
      await unitApi(`/calibrations/sessions/${enc(sessionId)}/abort`, { method: "POST" });
    } catch (err) {
      toast.error(err);
    }
    storeSession(null);
    onClose(false);
  };

  const result = step?.result || step?.metadata?.result;
  const finished = Boolean(result) || step?.step_type === "result";
  const metadata = step?.metadata || {};
  const actions = Array.isArray(metadata.actions) ? metadata.actions : [];
  const chart = metadata.chart;
  const image = busy && metadata.loading_images?.length ? metadata.loading_images[0] : metadata.image;
  const guidance = typeof metadata.guidance?.message === "string" ? metadata.guidance : null;
  const missing = missingFields(step, values);
  const fields = (step?.fields || []).filter((field) => !isHidden(step, field));

  return (
    <div className="session" role="dialog" aria-label={title}>
      <div className="session-head">
        <h2 className="truncate grow">{title}</h2>
        {finished || !sessionId ? (
          <button type="button" className="btn" onClick={() => onClose(finished)}>
            Close
          </button>
        ) : (
          <button type="button" className="btn danger" onClick={abort}>
            Abort
          </button>
        )}
      </div>

      <div className={`session-body ${chart ? "with-chart" : ""}`}>
        <div className="session-main">
          {step && <h3>{step.title || "Calibration step"}</h3>}
          {error && <div className="banner">{error}</div>}
          {busy && (
            <div className="busy-note" role="status">
              {step ? `Working on "${step.title || "this step"}". This can take a few minutes.` : "Starting..."}
            </div>
          )}
          {finished && (
            <div className="done-note">
              <Icon name="check" /> Calibration complete
              {resultNames(result).length > 0 && <span className="sub"> · saved as {resultNames(result).join(", ")}</span>}
            </div>
          )}
          {image?.src && (
            <figure className="step-image">
              <img src={image.src} alt={image.alt || ""} decoding="async" />
              {image.caption && <figcaption className="sub">{image.caption}</figcaption>}
            </figure>
          )}
          {guidance && (
            <div className="guidance">
              {guidance.title && <strong>{guidance.title}</strong>}
              <p>{guidance.message}</p>
            </div>
          )}
          {step?.body && <p className="step-body">{step.body}</p>}
          {metadata.table && <StepTable table={metadata.table} />}
          {fields.length > 0 && (
            <div className="form-grid">
              {fields.map((field) => (
                <StepField
                  key={`${step.step_id}-${field.name}`}
                  step={step}
                  field={field}
                  value={values[field.name]}
                  onChange={(value) => setValues((previous) => ({ ...previous, [field.name]: value }))}
                />
              ))}
            </div>
          )}
          {!step && !busy && !error && <Empty>Nothing to show.</Empty>}
        </div>
        {chart && Array.isArray(chart.series) && chart.series.length > 0 && (
          <div className="session-chart">
            <XYChart series={chart.series} title={chart.title} xLabel={chart.x_label} yLabel={chart.y_label} />
          </div>
        )}
      </div>

      <div className="session-foot">
        {missing.length > 0 && !busy && <span className="sub grow">Set {missing.map((f) => f.label).join(", ")}</span>}
        <span className="grow" />
        {!finished &&
          actions.map((action) => (
            <AsyncButton key={action.label} className="btn" disabled={busy} onClick={() => advance(action.inputs)}>
              {action.label}
            </AsyncButton>
          ))}
        {finished ? (
          <button type="button" className="btn primary" onClick={() => onClose(true)}>
            Done
          </button>
        ) : (
          <button
            type="button"
            className="btn primary"
            disabled={!step || busy || missing.length > 0}
            onClick={() => advance(formatInputs(step, values))}
          >
            {busy ? "Working..." : metadata.primary_action_label || "Continue"}
          </button>
        )}
      </div>
    </div>
  );
}
