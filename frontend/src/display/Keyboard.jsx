import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Icon, useToast } from "./ui";

// Pop-up keyboard. Fields call openKeyboard({...}) instead of focusing a native
// input, so the whole screen becomes the editor: the value is always visible
// and no system keyboard or scroll-into-view is needed.
//
// Character keys act on pointerdown for responsiveness on a laggy display.
// Keys that close the keyboard act on click, so the release can't land on
// whatever was underneath.

const KeyboardContext = createContext(null);

export const useKeyboard = () => useContext(KeyboardContext);

const ALPHA = [
  ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "BACK"],
  ["a", "s", "d", "f", "g", "h", "j", "k", "l", "'", "DONE"],
  ["SHIFT", "z", "x", "c", "v", "b", "n", "m", ",", ".", "-"],
  ["SYM", "SPACE", "_", "LEFT", "RIGHT"],
];

const SYMBOLS = [
  ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "BACK"],
  ["@", "&", "(", ")", ":", ";", "\"", "!", "?", "=", "DONE"],
  ["ABC", "*", "+", "/", "%", "#", "$", "~", ",", ".", "-"],
  ["ABC", "SPACE", "_", "LEFT", "RIGHT"],
];

const KEY_CLASS = {
  BACK: "alt w15",
  DONE: "primary w15",
  SHIFT: "alt w15",
  SYM: "alt w15",
  ABC: "alt w15",
  SPACE: "w5",
  LEFT: "alt",
  RIGHT: "alt",
};

export function validateNumber(text, { min, max, allowNegative = true, integer = false } = {}) {
  if (text.trim() === "") return "Enter a number.";
  const value = Number(text);
  if (!Number.isFinite(value)) return "Not a valid number.";
  if (!allowNegative && value < 0) return "Must not be negative.";
  if (integer && !Number.isInteger(value)) return "Must be a whole number.";
  if (min !== undefined && min !== null && value < min) return `Must be at least ${min}.`;
  if (max !== undefined && max !== null && value > max) return `Must be at most ${max}.`;
  return null;
}

// Pure editing operations, shared by on-screen and physical keys.
export function applyKey(state, key) {
  const { text, caret, fresh } = state;
  // The first keystroke on a pre-filled number replaces it, like a selected field.
  const base = fresh ? "" : text;
  const at = fresh ? 0 : caret;
  switch (key) {
    case "BACK":
      if (fresh) return { text: "", caret: 0, fresh: false };
      if (caret === 0) return state;
      return { text: text.slice(0, caret - 1) + text.slice(caret), caret: caret - 1, fresh: false };
    case "CLEAR":
      return { text: "", caret: 0, fresh: false };
    case "LEFT":
      return { text, caret: Math.max(0, caret - 1), fresh: false };
    case "RIGHT":
      return { text, caret: Math.min(text.length, caret + 1), fresh: false };
    case "NEGATE":
      if (text.startsWith("-")) return { text: text.slice(1), caret: Math.max(0, caret - 1), fresh: false };
      return { text: `-${text}`, caret: caret + 1, fresh: false };
    case "SPACE":
      return applyKey(state, " ");
    default:
      return { text: base.slice(0, at) + key + base.slice(at), caret: at + key.length, fresh: false };
  }
}

function Key({ value, label, className = "", onPress, onRelease, repeat = false, ariaLabel }) {
  const timers = useRef([]);
  const [down, setDown] = useState(false);

  const stop = () => {
    timers.current.forEach((timer) => clearTimeout(timer));
    timers.current = [];
    setDown(false);
  };

  useEffect(() => stop, []);

  const handlePointerDown = (event) => {
    event.preventDefault();
    setDown(true);
    if (!onPress) return;
    onPress(value);
    if (repeat) {
      const tick = () => {
        onPress(value);
        timers.current.push(setTimeout(tick, 70));
      };
      timers.current.push(setTimeout(tick, 450));
    }
  };

  return (
    <button
      type="button"
      className={`key ${className} ${down ? "down" : ""}`}
      aria-label={ariaLabel || (typeof label === "string" ? label : value)}
      onPointerDown={handlePointerDown}
      onPointerUp={stop}
      onPointerLeave={stop}
      onPointerCancel={stop}
      onClick={onRelease ? () => onRelease(value) : undefined}
    >
      {label ?? value}
    </button>
  );
}

const BackspaceGlyph = <Icon name="backspace" />;
const ShiftGlyph = <Icon name="shift" />;

function Editor({ request, onClose }) {
  const isNumber = request.type === "number";
  const [state, setState] = useState(() => ({
    text: request.value ?? "",
    caret: (request.value ?? "").length,
    fresh: isNumber && Boolean(request.value),
  }));
  const [shift, setShift] = useState("off"); // off | once | lock
  const [layer, setLayer] = useState("alpha");
  const [error, setError] = useState(null);
  const lastShiftTap = useRef(0);

  const press = useCallback((key) => {
    setError(null);
    setState((previous) => applyKey(previous, key));
  }, []);

  const pressChar = useCallback(
    (key) => {
      const upper = shift !== "off" && layer === "alpha";
      press(upper ? key.toUpperCase() : key);
      if (shift === "once") setShift("off");
    },
    [layer, press, shift],
  );

  const submit = useCallback(() => {
    const text = isNumber ? state.text.trim() : state.text;
    const problem = isNumber
      ? validateNumber(text, request)
      : request.validate?.(text) ?? null;
    if (problem) {
      setError(problem);
      return;
    }
    onClose();
    request.onSubmit(text);
  }, [isNumber, onClose, request, state.text]);

  const tapShift = () => {
    const now = Date.now();
    if (now - lastShiftTap.current < 400) {
      setShift("lock");
    } else {
      setShift((previous) => (previous === "off" ? "once" : "off"));
    }
    lastShiftTap.current = now;
  };

  // A physical keyboard also works (useful with a USB keyboard and in development).
  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      const map = { Backspace: "BACK", ArrowLeft: "LEFT", ArrowRight: "RIGHT" };
      if (event.key === "Enter") {
        event.preventDefault();
        submit();
      } else if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      } else if (map[event.key]) {
        event.preventDefault();
        press(map[event.key]);
      } else if (event.key.length === 1) {
        if (isNumber && !/[0-9.\-eE]/.test(event.key)) return;
        event.preventDefault();
        press(event.key);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isNumber, onClose, press, submit]);

  const before = state.text.slice(0, state.caret);
  const after = state.text.slice(state.caret);

  const renderTextKey = (key) => {
    switch (key) {
      case "BACK":
        return <Key key={key} value="BACK" label={BackspaceGlyph} ariaLabel="Backspace" className={KEY_CLASS.BACK} onPress={press} repeat />;
      case "DONE":
        return <Key key={key} value="DONE" label={request.submitLabel || "Done"} className={KEY_CLASS.DONE} onRelease={submit} />;
      case "SHIFT":
        return (
          <Key
            key={key}
            value="SHIFT"
            label={ShiftGlyph}
            ariaLabel="Shift"
            className={`${KEY_CLASS.SHIFT} ${shift !== "off" ? "on" : ""}`}
            onPress={tapShift}
          />
        );
      case "SYM":
        return <Key key={key} value="SYM" label="?123" className={KEY_CLASS.SYM} onPress={() => setLayer("symbols")} />;
      case "ABC":
        return <Key key={key} value="ABC" label="ABC" className={KEY_CLASS.ABC} onPress={() => setLayer("alpha")} />;
      case "SPACE":
        return <Key key={key} value="SPACE" label="space" className={KEY_CLASS.SPACE} onPress={press} />;
      case "LEFT":
        return <Key key={key} value="LEFT" label={<Icon name="back" />} ariaLabel="Move left" className={KEY_CLASS.LEFT} onPress={press} repeat />;
      case "RIGHT":
        return <Key key={key} value="RIGHT" label={<Icon name="forward" />} ariaLabel="Move right" className={KEY_CLASS.RIGHT} onPress={press} repeat />;
      default: {
        const shown = shift !== "off" && layer === "alpha" ? key.toUpperCase() : key;
        return <Key key={key} value={key} label={shown} onPress={pressChar} />;
      }
    }
  };

  const rows = layer === "alpha" ? ALPHA : SYMBOLS;

  return (
    <div className="kb" role="dialog" aria-label={`Edit ${request.label}`}>
      <div className="kb-head">
        <button type="button" className="btn" onClick={onClose}>
          Cancel
        </button>
        <div className="kb-input">
          <span className="kb-label">{request.label}</span>
          <span className="kb-text">
            {state.fresh ? (
              <span style={{ background: "var(--selection)" }}>{state.text}</span>
            ) : (
              <>
                {before}
                <span className="caret" />
                {after}
              </>
            )}
            {!state.text && request.placeholder && <span className="placeholder">{request.placeholder}</span>}
            {request.unit && <span className="unit">{request.unit}</span>}
          </span>
        </div>
        <button type="button" className="btn primary" onClick={submit}>
          {request.submitLabel || "Done"}
        </button>
      </div>
      <div className={`kb-message ${error ? "error" : ""}`} role={error ? "alert" : undefined}>
        {error || request.hint || ""}
      </div>

      {isNumber ? (
        <>
          {request.presets?.length > 0 && (
            <div className="presets">
              {request.presets.map((preset) => (
                <Key
                  key={preset}
                  value={String(preset)}
                  label={`${preset}${request.unit ? ` ${request.unit}` : ""}`}
                  className="alt"
                  onPress={(value) => {
                    setError(null);
                    setState({ text: value, caret: value.length, fresh: true });
                  }}
                />
              ))}
            </div>
          )}
          <div className="kb-numpad">
            {["7", "8", "9"].map((digit) => <Key key={digit} value={digit} onPress={press} />)}
            <Key value="BACK" label={BackspaceGlyph} ariaLabel="Backspace" className="alt" onPress={press} repeat />
            {["4", "5", "6"].map((digit) => <Key key={digit} value={digit} onPress={press} />)}
            <Key value="CLEAR" label="Clear" className="alt" onPress={press} />
            {["1", "2", "3"].map((digit) => <Key key={digit} value={digit} onPress={press} />)}
            <Key value="DONE" label={request.submitLabel || "Done"} className="primary span2" onRelease={submit} />
            {request.allowNegative === false ? (
              <Key value="00" label="" className="alt" />
            ) : (
              <Key value="NEGATE" label="±" ariaLabel="Toggle sign" className="alt" onPress={press} />
            )}
            <Key value="0" onPress={press} />
            <Key value="." onPress={press} />
          </div>
        </>
      ) : (
        <div className="kb-keys">
          {rows.map((row, index) => (
            <div className="kb-row" key={index}>
              {row.map(renderTextKey)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function KeyboardProvider({ children }) {
  const [request, setRequest] = useState(null);
  const close = useCallback(() => setRequest(null), []);
  const open = useCallback((options) => setRequest({ type: "text", ...options, id: Date.now() }), []);

  return (
    <KeyboardContext.Provider value={open}>
      {children}
      {request && <Editor key={request.id} request={request} onClose={close} />}
    </KeyboardContext.Provider>
  );
}

// A tappable value that edits through the on-screen keyboard.
// onCommit may return a promise; the new value shows as pending until it settles.
export function EditField({
  label,
  value,
  unit,
  type = "number",
  onCommit,
  disabled,
  placeholder,
  className = "",
  ...keyboardOptions
}) {
  const openKeyboard = useKeyboard();
  const toast = useToast();
  const [pendingValue, setPendingValue] = useState(null);
  const shown = pendingValue ?? value;

  // Keep showing the submitted value until the confirmed value arrives (often via MQTT,
  // after the request resolves), so the field doesn't flicker back to the old value.
  const settleTimer = useRef(null);
  useEffect(() => {
    setPendingValue(null);
    clearTimeout(settleTimer.current);
  }, [value]);
  useEffect(() => () => clearTimeout(settleTimer.current), []);
  const empty = shown === null || shown === undefined || shown === "";

  const open = () =>
    openKeyboard({
      label,
      unit,
      type,
      value: value === null || value === undefined ? "" : String(value),
      ...keyboardOptions,
      onSubmit: (next) => {
        const result = onCommit(type === "number" ? Number(next) : next);
        if (result && typeof result.then === "function") {
          setPendingValue(next);
          result.then(
            () => {
              settleTimer.current = setTimeout(() => setPendingValue(null), 4000);
            },
            (error) => {
              setPendingValue(null);
              toast.error(error);
            },
          );
        }
      },
    });

  return (
    <button className={`field ${className}`} onClick={open} disabled={disabled}>
      <span className="field-label">{label}</span>
      <span className="field-value">
        {empty ? <span className="placeholder">{placeholder || "Set"}</span> : shown}
        {!empty && unit && <small>{unit}</small>}
        {pendingValue !== null && <small>saving...</small>}
        <Icon name="edit" className="edit" />
      </span>
    </button>
  );
}
