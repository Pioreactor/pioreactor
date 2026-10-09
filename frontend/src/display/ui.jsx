import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { stateDisplay } from "../utils/color";
import AddIcon from "@mui/icons-material/Add";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import BackspaceOutlinedIcon from "@mui/icons-material/BackspaceOutlined";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import ContrastOutlinedIcon from "@mui/icons-material/ContrastOutlined";
import DashboardOutlinedIcon from "@mui/icons-material/DashboardOutlined";
import EditIcon from "@mui/icons-material/Edit";
import FlareIcon from "@mui/icons-material/Flare";
import KeyboardCapslockIcon from "@mui/icons-material/KeyboardCapslock";
import ListAltOutlinedIcon from "@mui/icons-material/ListAltOutlined";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import PlayCircleOutlinedIcon from "@mui/icons-material/PlayCircleOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import ExperimentProfileIcon from "../components/ExperimentProfileIcon";
import ExperimentsIcon from "../components/ExperimentsIcon";
import PioreactorIcon from "../components/PioreactorIcon";

// The same icons as the main UI, so both interfaces read alike.
const ICONS = {
  units: PioreactorIcon,
  chart: DashboardOutlinedIcon,
  experiments: ExperimentsIcon,
  experiment: PlayCircleOutlinedIcon,
  profiles: ExperimentProfileIcon,
  logs: ListAltOutlinedIcon,
  system: SettingsOutlinedIcon,
  back: ArrowBackIcon,
  forward: ArrowForwardIcon,
  close: CloseIcon,
  play: PlayArrowIcon,
  check: CheckIcon,
  identify: FlareIcon,
  add: AddIcon,
  stop: CancelIcon,
  refresh: RefreshIcon,
  edit: EditIcon,
  appearance: ContrastOutlinedIcon,
  backspace: BackspaceOutlinedIcon,
  shift: KeyboardCapslockIcon,
};

export function Icon({ name, className = "" }) {
  const Component = ICONS[name];
  return <Component className={`icon ${className}`} fontSize="inherit" aria-hidden="true" />;
}

/* ---------- Toasts ---------- */

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);

  const show = useCallback((message, kind = "info") => {
    clearTimeout(timer.current);
    setToast({ message, kind });
    timer.current = setTimeout(() => setToast(null), kind === "error" ? 6000 : 2500);
  }, []);

  const api = useMemo(() => {
    const fn = (message) => show(message, "info");
    fn.error = (error) => show(typeof error === "string" ? error : error?.message || "Something went wrong.", "error");
    return fn;
  }, [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {toast && (
        <div className={`toast ${toast.kind}`} role="status" onClick={() => setToast(null)}>
          {toast.message}
        </div>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ---------- Confirm dialog ---------- */

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);

  const confirm = useCallback(
    (options) => new Promise((resolve) => setRequest({ ...options, resolve })),
    [],
  );

  const close = (result) => {
    request?.resolve(result);
    setRequest(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <div className="backdrop" onClick={() => close(false)}>
          <div className="dialog" role="alertdialog" onClick={(event) => event.stopPropagation()}>
            <h2>{request.title}</h2>
            {request.message && <p>{request.message}</p>}
            <div className="btn-row">
              <button className="btn" onClick={() => close(false)}>
                Cancel
              </button>
              <button className={`btn ${request.danger ? "danger solid" : "primary"}`} onClick={() => close(true)}>
                {request.confirmText || "Confirm"}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmContext);

/* ---------- Building blocks ---------- */

// Runs an async action, shows busy state, and reports failures in a toast.
export function AsyncButton({ onClick, className = "btn", children, disabled, ...props }) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const mounted = useRef(true);
  useEffect(() => () => {
    mounted.current = false;
  }, []);

  const handleClick = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await onClick();
    } catch (error) {
      toast.error(error);
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  return (
    <button {...props} className={`${className} ${busy ? "busy" : ""}`} disabled={disabled || busy} onClick={handleClick}>
      {children}
    </button>
  );
}

export function Sheet({ title, onClose, children, footer }) {
  return (
    <div className="backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-label={typeof title === "string" ? title : undefined} onClick={(event) => event.stopPropagation()}>
        <div className="sheet-head">
          <h2 className="truncate">{title}</h2>
          <button className="btn ghost icon-only" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function StateBadge({ state, pending }) {
  if (pending) return <span className="badge pending">{pending}</span>;
  const key = state && stateDisplay[state] ? state : "disconnected";
  return <span className={`badge ${key}`}>{stateDisplay[key].display}</span>;
}

export function Segmented({ options, value, onChange }) {
  return (
    <div className="segmented" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          role="tab"
          aria-selected={option.value === value}
          className={option.value === value ? "on" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          role="tab"
          aria-selected={tab.value === value}
          className={tab.value === value ? "on" : ""}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function ReadValue({ label, value, unit, className = "" }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className={`field ${className}`}>
      <span className="field-label">{label}</span>
      <span className="field-value">
        {empty ? <span className="placeholder">—</span> : value}
        {!empty && unit && <small>{unit}</small>}
      </span>
    </div>
  );
}
