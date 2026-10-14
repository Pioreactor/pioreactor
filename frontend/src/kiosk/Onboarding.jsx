import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { validateUnitName } from "./cluster";
import { useKiosk } from "./context";
import { useAsync } from "./hooks";
import { Icon } from "./icons";
import { useKeyboard } from "./Keyboard";
import {
  connectWifi,
  finishOnboarding,
  getModel,
  getOnboarding,
  getWifiStatus,
  listModels,
  pendingName,
  renameUnit,
  resetOnboarding,
  scanWifi,
  setModel,
} from "./onboardingApi";
import { navigate } from "./router";
import { AsyncButton, Empty, useToast } from "./ui";

// First-boot setup, full screen: Name, Wi-Fi (optional), Model, Ready. Shown on
// every boot until finished, and again from System. See KIOSK.md, "Onboarding".

const STEPS = ["Name", "Wi-Fi", "Model", "Ready"];

function StepIndicator({ current }) {
  return (
    <ol className="steps" aria-label="Setup steps">
      {STEPS.map((label, index) => (
        <li
          key={label}
          className={`step ${index === current ? "current" : index < current ? "done" : ""}`}
          aria-current={index === current ? "step" : undefined}
        >
          {index < current ? <Icon name="check" /> : <span className="num">{index + 1}</span>}
          {label}
        </li>
      ))}
    </ol>
  );
}

function Frame({ step, children, footer }) {
  const { unit } = useKiosk();
  return (
    <div className="onboarding">
      <header className="ob-head">
        <Icon name="pioreactor" />
        <h1 className="truncate">Set up {unit}</h1>
        {step >= 0 && <StepIndicator current={step} />}
      </header>
      <main className="ob-body">
        <div className="ob-inner">{children}</div>
      </main>
      <footer className="ob-foot">{footer}</footer>
    </div>
  );
}

function BackButton({ onBack }) {
  return (
    <button type="button" className="btn" onClick={onBack}>
      <Icon name="back" />
      Back
    </button>
  );
}

function Row({ title, sub, children }) {
  return (
    <div className="list-row">
      <div className="grow">
        <div className="strong truncate">{title}</div>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {children && <div className="row-actions">{children}</div>}
    </div>
  );
}

/* ---------- Steps ---------- */

function Welcome({ onNext }) {
  return (
    <Frame
      step={-1}
      footer={
        <>
          <span className="grow" />
          <button type="button" className="btn primary" onClick={onNext}>
            Get started
          </button>
        </>
      }
    >
      <div className="ob-welcome">
        <Icon name="pioreactor" className="ob-hero" />
        <h2>Welcome</h2>
      </div>
    </Frame>
  );
}

function NameStep({ summary, onBack, onNext }) {
  const { unit } = useKiosk();
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const [name, setName] = useState(summary.name);
  const [busy, setBusy] = useState(false);
  const renamed = name !== unit;

  const rename = () =>
    openKeyboard({
      label: "New name",
      type: "text",
      value: name,
      submitLabel: "Rename",
      validate: (raw) => validateUnitName(raw) || (raw.trim() === name ? "That's already its name." : null),
      onSubmit: async (raw) => {
        setBusy(true);
        try {
          const { hostname } = await renameUnit(raw.trim());
          setName(hostname);
        } catch (error) {
          toast.error(error);
        } finally {
          setBusy(false);
        }
      },
    });

  return (
    <Frame
      step={0}
      footer={
        <>
          <BackButton onBack={onBack} />
          <span className="grow" />
          <button type="button" className="btn primary" disabled={busy} onClick={() => onNext({ name })}>
            Next
          </button>
        </>
      }
    >
      <h2>Name</h2>
      <div className="list">
        <Row title={name} sub={renamed ? `Replaces ${unit} after the next restart.` : "Current name"}>
          <button type="button" className="btn" disabled={busy} onClick={rename}>
            {busy ? "Renaming..." : "Rename..."}
          </button>
        </Row>
      </div>
    </Frame>
  );
}

const signalLabel = (signal) => (signal >= 70 ? "Strong" : signal >= 45 ? "Good" : "Weak");

function networkSummary(status) {
  if (status?.connected) return { title: `Connected to ${status.ssid}`, sub: null, label: `Wi-Fi: ${status.ssid}` };
  if (status?.ethernet) return { title: "Connected by Ethernet", sub: null, label: "Ethernet" };
  return { title: "No network", sub: null, label: "No network" };
}

function WifiStep({ onBack, onNext }) {
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const status = useAsync(() => getWifiStatus(), []);
  const networks = useAsync(() => scanWifi(), []);
  const [joining, setJoining] = useState(null);
  const current = status.data;
  const online = Boolean(current?.connected || current?.ethernet);
  const summary = networkSummary(current);

  const join = async (ssid, password = "") => {
    setJoining(ssid);
    try {
      await connectWifi(ssid, password);
      toast(`Connected to ${ssid}`);
      status.reload();
    } catch (error) {
      toast.error(error);
    } finally {
      setJoining(null);
    }
  };

  const pick = (network) => {
    if (joining || current?.ssid === network.ssid) return;
    if (!network.secure) {
      join(network.ssid);
      return;
    }
    openKeyboard({
      label: `Password for ${network.ssid}`,
      type: "text",
      submitLabel: "Connect",
      validate: (raw) => (raw.length >= 8 ? null : "Passwords are at least 8 characters."),
      onSubmit: (password) => join(network.ssid, password),
    });
  };

  return (
    <Frame
      step={1}
      footer={
        <>
          <BackButton onBack={onBack} />
          <span className="grow" />
          {online ? (
            <button type="button" className="btn primary" onClick={() => onNext({ network: summary.label })}>
              Next
            </button>
          ) : (
            <button type="button" className="btn" onClick={() => onNext({ network: summary.label })}>
              Skip
            </button>
          )}
        </>
      }
    >
      <h2>Wi-Fi (optional)</h2>
      <div className="list">
        <Row title={status.data ? summary.title : "Checking..."} sub={status.data ? summary.sub : null} />
      </div>

      <h3 className="section-title">Networks</h3>
      <div className="list">
        {networks.loading && <Row title="Scanning..." />}
        {!networks.loading && networks.error && <Row title="Scan failed" sub={networks.error} />}
        {!networks.loading && networks.data?.length === 0 && <Row title="No networks found" />}
        {!networks.loading &&
          (networks.data || []).map((network) => {
            const connected = current?.connected && current.ssid === network.ssid;
            return (
              <button
                type="button"
                key={network.ssid}
                className="list-row"
                disabled={Boolean(joining)}
                onClick={() => pick(network)}
              >
                <span className="grow">
                  <span className="strong truncate">{network.ssid}</span>
                  <span className="sub">
                    {signalLabel(network.signal)} signal · {network.secure ? "Secured" : "Open"}
                  </span>
                </span>
                {joining === network.ssid && <span className="badge pending">Connecting...</span>}
                {connected && <span className="badge ready">Connected</span>}
              </button>
            );
          })}
        <button type="button" className="list-row add-row" disabled={networks.loading} onClick={networks.reload}>
          <Icon name="refresh" />
          <span className="grow">Scan again</span>
        </button>
      </div>
    </Frame>
  );
}

function ModelStep({ onBack, onNext }) {
  const { isLeader, worker } = useKiosk();
  const toast = useToast();
  const current = useAsync(() => getModel(), []);
  const models = useAsync(() => listModels({ isLeader }), [isLeader]);
  const [picked, setPicked] = useState(null);
  const [saving, setSaving] = useState(false);

  const key = (m) => (m ? `${m.model_name}::${m.model_version}` : null);
  const currentKey = key(current.data);
  // Without a model of its own, start from the leader's record of it (what the unit would adopt).
  const selectedKey = picked ?? currentKey ?? key(worker?.model_name ? worker : null);
  const rows = (models.data || []).filter((m) => !m.is_legacy || key(m) === currentKey);
  const selected = rows.find((m) => key(m) === selectedKey) || null;

  const next = async () => {
    if (!selected) return;
    if (selectedKey !== currentKey) {
      setSaving(true);
      try {
        await setModel(selected.model_name, selected.model_version);
      } catch (error) {
        toast.error(error);
        setSaving(false);
        return;
      }
    }
    onNext({ model: selected.display_name });
  };

  return (
    <Frame
      step={2}
      footer={
        <>
          <BackButton onBack={onBack} />
          <span className="grow" />
          <button type="button" className="btn primary" disabled={!selected || saving} onClick={next}>
            {saving ? "Saving..." : "Next"}
          </button>
        </>
      }
    >
      <h2>Model</h2>
      {(models.loading || current.loading) && <Empty>Loading models...</Empty>}
      {models.error && <Empty>Could not load models: {models.error}</Empty>}
      {!models.loading && !current.loading && rows.length > 0 && (
        <div className="list">
          {rows.map((m) => (
            <button
              type="button"
              key={key(m)}
              className={`list-row pick ${key(m) === selectedKey ? "on" : ""}`}
              aria-pressed={key(m) === selectedKey}
              onClick={() => setPicked(key(m))}
            >
              <span className="check">{key(m) === selectedKey && <Icon name="check" />}</span>
              <span className="grow">
                <span className="strong truncate">{m.display_name}</span>
              </span>
            </button>
          ))}
          {!selected && <div className="list-row muted">Choose a model.</div>}
        </div>
      )}
    </Frame>
  );
}

function ReadyStep({ summary, onBack, onDone }) {
  const { unit, role, leaderHostname } = useKiosk();
  const name = summary.name;

  const lead = {
    standalone: `${name} is ready.`,
    leader: `${name} is ready, and leads a cluster.`,
    worker: `${name} is ready, in ${leaderHostname}'s cluster.`,
    unjoined: `${name} is ready. Add it from a leader's Cluster page.`,
  }[role];

  const finish = async () => {
    await finishOnboarding();
    navigate("");
    onDone();
  };

  return (
    <Frame
      step={3}
      footer={
        <>
          <BackButton onBack={onBack} />
          <span className="grow" />
          <AsyncButton className="btn primary" onClick={finish}>
            Finish
          </AsyncButton>
        </>
      }
    >
      <h2>Ready</h2>
      <p className="muted">{lead}</p>
      <div className="list">
        <Row title="Name" sub={name !== unit ? `${name}, after the next restart` : name} />
        <Row title="Network" sub={summary.network} />
        <Row title="Model" sub={summary.model} />
      </div>
    </Frame>
  );
}

function Onboarding({ onDone }) {
  const { unit } = useKiosk();
  const [step, setStep] = useState(-1); // -1: welcome
  const [summary, setSummary] = useState(() => ({ name: pendingName() || unit, network: null, model: null }));

  const back = () => setStep((s) => s - 1);
  const next = (patch = {}) => {
    setSummary((previous) => ({ ...previous, ...patch }));
    setStep((s) => s + 1);
  };

  if (step === -1) return <Welcome onNext={() => next()} />;
  if (step === 0) return <NameStep summary={summary} onBack={back} onNext={next} />;
  if (step === 1) return <WifiStep onBack={back} onNext={next} />;
  if (step === 2) return <ModelStep onBack={back} onNext={next} />;
  return <ReadyStep summary={summary} onBack={back} onDone={onDone} />;
}

/* ---------- Gate ---------- */

const SetupContext = createContext(null);

// Starts setup again (System page).
export const useRestartSetup = () => useContext(SetupContext);

export function OnboardingGate({ children }) {
  const [state, setState] = useState(null);

  useEffect(() => {
    getOnboarding()
      .then(setState)
      .catch(() => setState({ done: true })); // never lock the screen behind setup
  }, []);

  const restart = useCallback(async () => {
    await resetOnboarding();
    setState({ done: false });
  }, []);

  if (!state) return <div className="boot">Starting...</div>;
  if (!state.done) return <Onboarding onDone={() => setState({ done: true })} />;
  return <SetupContext.Provider value={restart}>{children}</SetupContext.Provider>;
}
