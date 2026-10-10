import { useEffect, useState } from "react";
import { Icon } from "../icons";
import { EditField } from "../Keyboard";
import { getAutomationDescriptors, useJobControl } from "../jobs";
import { AsyncButton, Empty, ReadValue, Sheet, useToast } from "../ui";

// Same preferred defaults as the main UI's automation dialog.
const DEFAULT_AUTOMATIONS = { temperature: "thermostat", dosing: "chemostat", led: "light_dark_cycle" };
const TYPE_LABELS = { temperature: "temperature", dosing: "dosing", led: "LED" };

function defaultsFor(automation) {
  return Object.fromEntries((automation?.fields || []).map((field) => [field.key, field.default]));
}

function missingRequired(automation, settings) {
  return (automation?.fields || []).filter(
    (field) => field.required && !field.disabled && [null, undefined, ""].includes(settings[field.key]),
  );
}

function FieldInput({ field, value, onChange }) {
  if (field.disabled) {
    return <ReadValue className="wide" label={field.label} value={value} unit={field.unit} />;
  }
  if (field.type === "boolean") {
    return (
      <button type="button" className={`btn block ${value ? "primary" : ""}`} onClick={() => onChange(!value)}>
        {value ? <Icon name="check" /> : null}
        {field.label}: {value ? "on" : "off"}
      </button>
    );
  }
  if (field.type === "select") {
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

export default function AutomationSheet({ automationType, onClose, onStarted }) {
  const toast = useToast();
  const control = useJobControl();
  const [automations, setAutomations] = useState(null);
  const [selected, setSelected] = useState(null);
  const [settings, setSettings] = useState({});

  useEffect(() => {
    let ignore = false;
    getAutomationDescriptors(automationType)
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
  }, [automationType, toast]);

  const automation = automations?.find((a) => a.automation_name === selected);
  const missing = missingRequired(automation, settings);

  const choose = (candidate) => {
    setSelected(candidate.automation_name);
    setSettings(defaultsFor(candidate));
  };

  const start = async () => {
    const options = Object.fromEntries(Object.entries(settings).filter(([, value]) => value !== null && value !== undefined));
    await control.run(`${automationType}_automation`, { options: { automation_name: selected, ...options } });
    toast(`Starting ${automation.display_name}...`);
    onStarted();
  };

  return (
    <Sheet
      title={`Start ${TYPE_LABELS[automationType] || automationType} automation`}
      onClose={onClose}
      footer={
        <>
          {missing.length > 0 && <span className="error-text grow">Set {missing.map((f) => f.label).join(", ")}</span>}
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <AsyncButton className="btn primary" onClick={start} disabled={!automation || missing.length > 0}>
            <Icon name="play" />
            Start
          </AsyncButton>
        </>
      }
    >
      {!automations && <Empty>Loading...</Empty>}
      {automations && (
        <div className="form-grid">
          <div className="chips wrap">
            {automations.map((candidate) => (
              <button
                type="button"
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
