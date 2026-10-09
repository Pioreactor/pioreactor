import { useEffect, useState } from "react";
import { getAutomationDescriptors, runPioreactorJob } from "../../utils/jobs";
import { AsyncButton, Icon, ReadValue, Sheet, useToast } from "../ui";
import { EditField } from "../Keyboard";

// Same preferred defaults as the main UI's automation dialog.
const DEFAULT_AUTOMATIONS = { temperature: "thermostat", dosing: "chemostat", led: "light_dark_cycle" };
const TYPE_LABELS = { temperature: "temperature", dosing: "dosing", led: "LED" };

function defaultsFor(automation) {
  return Object.fromEntries((automation?.fields || []).map((field) => [field.key, field.default]));
}

function missingRequired(automation, settings) {
  return (automation?.fields || []).filter(
    (field) => field.required && !field.disabled && (settings[field.key] === null || settings[field.key] === undefined || settings[field.key] === ""),
  );
}

function FieldInput({ field, value, onChange }) {
  if (field.disabled) {
    return <ReadValue className="wide" label={field.label} value={value} unit={field.unit} />;
  }
  if (field.type === "boolean") {
    return (
      <button className={`btn block ${value ? "primary" : ""}`} onClick={() => onChange(!value)}>
        {value ? <Icon name="check" /> : null}
        {field.label}: {value ? "on" : "off"}
      </button>
    );
  }
  if (field.type === "select") {
    return (
      <div>
        <div className="field-label muted">{field.label}</div>
        <div className="chips" style={{ flexWrap: "wrap" }}>
          {(field.options || []).map((option) => (
            <button key={option} className={`chip ${option === value ? "on" : ""}`} onClick={() => onChange(option)}>
              {option}
            </button>
          ))}
        </div>
      </div>
    );
  }
  return (
    <EditField
      className="wide"
      label={field.label}
      value={value}
      unit={field.unit}
      type={field.type === "numeric" ? "number" : "text"}
      hint={field.description}
      placeholder={field.required ? "Required" : "Not set"}
      onCommit={onChange}
    />
  );
}

export default function AutomationSheet({ unit, experiment, automationType, onClose, onStarted }) {
  const toast = useToast();
  const [automations, setAutomations] = useState(null);
  const [selected, setSelected] = useState(null);
  const [settings, setSettings] = useState({});

  useEffect(() => {
    let ignore = false;
    getAutomationDescriptors(unit, automationType)
      .then((list) => {
        if (ignore) return;
        setAutomations(list);
        const preferred = list.find((a) => a.automation_name === DEFAULT_AUTOMATIONS[automationType]) || list[0];
        if (preferred) {
          setSelected(preferred.automation_name);
          setSettings(defaultsFor(preferred));
        }
      })
      .catch((error) => !ignore && toast.error(error));
    return () => {
      ignore = true;
    };
  }, [unit, automationType, toast]);

  const automation = automations?.find((a) => a.automation_name === selected);
  const missing = missingRequired(automation, settings);

  const choose = (candidate) => {
    setSelected(candidate.automation_name);
    setSettings(defaultsFor(candidate));
  };

  const start = async () => {
    const options = Object.fromEntries(Object.entries(settings).filter(([, value]) => value !== null && value !== undefined));
    await runPioreactorJob(unit, experiment, `${automationType}_automation`, [], { automation_name: selected, ...options });
    toast(`Starting ${automation.display_name}...`);
    onStarted();
  };

  return (
    <Sheet
      title={`Start ${TYPE_LABELS[automationType] || automationType} automation`}
      onClose={onClose}
      footer={
        <>
          {missing.length > 0 && <span className="error-text" style={{ marginRight: "auto", alignSelf: "center" }}>Set {missing.map((f) => f.label).join(", ")}</span>}
          <button className="btn" onClick={onClose}>
            Cancel
          </button>
          <AsyncButton className="btn primary" onClick={start} disabled={!automation || missing.length > 0}>
            <Icon name="play" />
            Start
          </AsyncButton>
        </>
      }
    >
      {!automations && <div className="empty">Loading...</div>}
      {automations && (
        <div className="form-grid">
          <div className="chips" style={{ flexWrap: "wrap" }}>
            {automations.map((candidate) => (
              <button
                key={candidate.automation_name}
                className={`chip ${candidate.automation_name === selected ? "on" : ""}`}
                onClick={() => choose(candidate)}
              >
                {candidate.display_name}
              </button>
            ))}
          </div>
          {automation?.description && <p className="description">{automation.description}</p>}
          {(automation?.fields || []).map((field) => (
            <FieldInput
              key={`${selected}-${field.key}`}
              field={field}
              value={settings[field.key]}
              onChange={(value) => setSettings((previous) => ({ ...previous, [field.key]: value }))}
            />
          ))}
        </div>
      )}
    </Sheet>
  );
}
