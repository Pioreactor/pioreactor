import { createContext, memo, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Icon } from "./icons";

/* ---------- Toasts ---------- */

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toast, setToast] = useState(null);
  const timer = useRef(null);

  const show = useCallback((message, kind) => {
    clearTimeout(timer.current);
    setToast({ message, kind });
    timer.current = setTimeout(() => setToast(null), kind === "error" ? 7000 : 3000);
  }, []);

  useEffect(() => () => clearTimeout(timer.current), []);

  const api = useMemo(() => {
    const fn = (message) => show(message, "info");
    fn.error = (error) =>
      show(typeof error === "string" ? error : error?.message || "Something went wrong.", "error");
    return fn;
  }, [show]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {toast && (
        <button type="button" className={`toast ${toast.kind}`} role="status" onClick={() => setToast(null)}>
          {toast.message}
        </button>
      )}
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);

/* ---------- Confirm dialog ---------- */

const ConfirmContext = createContext(null);

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);

  const confirm = useCallback((options) => new Promise((resolve) => setRequest({ ...options, resolve })), []);

  const close = (result) => {
    request?.resolve(result);
    setRequest(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <div className="backdrop" onClick={() => close(false)}>
          <div className="dialog" role="alertdialog" aria-label={request.title} onClick={(event) => event.stopPropagation()}>
            <h2>{request.title}</h2>
            {request.message && <p>{request.message}</p>}
            <div className="btn-row end">
              <button type="button" className="btn" onClick={() => close(false)}>
                Cancel
              </button>
              <button
                type="button"
                className={`btn ${request.danger ? "danger solid" : "primary"}`}
                onClick={() => close(true)}
              >
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

// Runs an async action, shows a busy state, and reports failures in a toast.
export function AsyncButton({ onClick, className = "btn", children, disabled, busyLabel, ...props }) {
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const mounted = useRef(true);
  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

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
    <button
      type="button"
      {...props}
      className={`${className} ${busy ? "busy" : ""}`}
      disabled={disabled || busy}
      onClick={handleClick}
    >
      {busy && busyLabel ? busyLabel : children}
    </button>
  );
}

export function Sheet({ title, onClose, children, footer }) {
  return (
    <div className="backdrop" onClick={onClose}>
      <div className="sheet" role="dialog" aria-label={typeof title === "string" ? title : undefined} onClick={(event) => event.stopPropagation()}>
        <div className="sheet-head">
          <h2 className="truncate">{title}</h2>
          <button type="button" className="btn ghost icon-only" onClick={onClose} aria-label="Close">
            <Icon name="close" />
          </button>
        </div>
        <div className="sheet-body">{children}</div>
        {footer && <div className="sheet-foot">{footer}</div>}
      </div>
    </div>
  );
}

const STATE_LABELS = {
  init: "Starting",
  ready: "On",
  sleeping: "Paused",
  disconnected: "Off",
  lost: "Lost",
};

export const StateBadge = memo(function StateBadge({ state, pending }) {
  if (pending) return <span className="badge pending">{pending}</span>;
  const key = state in STATE_LABELS ? state : "disconnected";
  return <span className={`badge ${key}`}>{STATE_LABELS[key]}</span>;
});

export function Segmented({ options, value, onChange, label }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button
          type="button"
          key={option.value}
          role="radio"
          aria-checked={option.value === value}
          className={option.value === value ? "on" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export const ReadValue = memo(function ReadValue({ label, value, unit, className = "" }) {
  const empty = value === null || value === undefined || value === "";
  return (
    <div className={`field static ${className}`}>
      <span className="field-label">{label}</span>
      <span className="field-value">
        {empty ? <span className="placeholder">—</span> : value}
        {!empty && unit && <small>{unit}</small>}
      </span>
    </div>
  );
});

export function Empty({ children }) {
  return <div className="empty">{children}</div>;
}
