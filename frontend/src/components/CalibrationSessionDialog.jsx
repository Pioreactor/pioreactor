import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormLabel from "@mui/material/FormLabel";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import CloseIcon from "@mui/icons-material/Close";
import { Link } from "react-router";
import CalibrationSessionChart from "./CalibrationSessionChart";

const sessionStartEndpoint = (unit) =>
  `/api/workers/${unit}/calibrations/sessions`;
const sessionAdvanceEndpoint = (unit, sessionId) =>
  `/api/workers/${unit}/calibrations/sessions/${sessionId}/inputs`;
const sessionAbortEndpoint = (unit, sessionId) =>
  `/api/workers/${unit}/calibrations/sessions/${sessionId}/abort`;


function buildInitialValues(step) {
  const nextValues = {};
  if (!step || !Array.isArray(step.fields)) {
    return nextValues;
  }
  step.fields.forEach((field) => {
    if (field.field_type === "float_list") {
      if (Array.isArray(field.default)) {
        nextValues[field.name] = field.default.join(", ");
      } else {
        nextValues[field.name] = "";
      }
      return;
    }
    if (field.field_type === "bool") {
      nextValues[field.name] = Boolean(field.default);
      return;
    }
    if (field.default !== undefined && field.default !== null) {
      nextValues[field.name] = field.default;
    } else {
      nextValues[field.name] = "";
    }
  });
  return nextValues;
}


function formatInputs(step, values) {
  if (!step || !Array.isArray(step.fields)) {
    return {};
  }
  const output = {};
  step.fields.forEach((field) => {
    const rawValue = values[field.name];
    if (field.field_type === "bool") {
      if (field.name === "confirmed") {
        output[field.name] = true;
        return;
      }
      output[field.name] = Boolean(rawValue);
      return;
    }
    if (field.field_type === "float_list") {
      if (typeof rawValue === "string") {
        const parsed = rawValue
          .split(",")
          .map((value) => value.trim())
          .filter((value) => value.length > 0)
          .map((value) => Number(value));
        output[field.name] = parsed;
        return;
      }
      output[field.name] = Array.isArray(rawValue) ? rawValue : [];
      return;
    }
    if (field.field_type === "float") {
      output[field.name] = rawValue === "" ? rawValue : Number(rawValue);
      return;
    }
    if (field.field_type === "int") {
      output[field.name] = rawValue === "" ? rawValue : Number.parseInt(rawValue, 10);
      return;
    }
    output[field.name] = rawValue;
  });
  if (step.step_type === "action") {
    output.confirm = true;
  }
  return output;
}


export default function CalibrationSessionDialog({
  protocol,
  unit,
  open,
  onClose,
  onAbortSuccess,
  onAbortFailure,
  onStartFailure,
}) {
  const [sessionId, setSessionId] = React.useState(null);
  const [sessionStep, setSessionStep] = React.useState(null);
  const [sessionError, setSessionError] = React.useState("");
  const [sessionLoading, setSessionLoading] = React.useState(false);
  const [sessionValues, setSessionValues] = React.useState({});
  const startInFlightRef = React.useRef(false);

  const sessionResult = sessionStep?.result || sessionStep?.metadata?.result;
  const chartPayload = sessionStep?.metadata?.chart;
  const inlineActions = Array.isArray(sessionStep?.metadata?.actions)
    ? sessionStep.metadata.actions
    : [];
  const stepImage = sessionStep?.metadata?.image;

  const resetSessionState = React.useCallback(() => {
    setSessionId(null);
    setSessionStep(null);
    setSessionError("");
    setSessionLoading(false);
    setSessionValues({});
    startInFlightRef.current = false;
  }, []);

  const startSession = React.useCallback(async () => {
    if (!open || !protocol || !unit) {
      return;
    }
    if (startInFlightRef.current || sessionId) {
      return;
    }
    startInFlightRef.current = true;
    setSessionLoading(true);
    setSessionError("");
    try {
      const response = await fetch(sessionStartEndpoint(unit), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          protocol_name: protocol.protocolName,
          target_device: protocol.device,
        }),
      });

      if (!response.ok) {
        let errorMessage = `Failed to start session (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage = payload.error || payload.message || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      const nextSessionId = payload.session?.session_id;
      setSessionId(nextSessionId);
      if (payload.step) {
        setSessionStep(payload.step);
        setSessionValues(buildInitialValues(payload.step));
        return;
      }
      if (!nextSessionId) {
        throw new Error("Session started without a session id.");
      }
      const followUp = await fetch(`/api/workers/${unit}/calibrations/sessions/${nextSessionId}`);
      if (!followUp.ok) {
        throw new Error("Session started without a step payload.");
      }
      const followUpPayload = await followUp.json();
      if (!followUpPayload.step) {
        throw new Error("Session started without a step payload.");
      }
      setSessionStep(followUpPayload.step);
      setSessionValues(buildInitialValues(followUpPayload.step));
    } catch (err) {
      const message = err.message || "Failed to start session.";
      setSessionError(message);
      if (onStartFailure) {
        onStartFailure(message);
      }
    } finally {
      setSessionLoading(false);
      startInFlightRef.current = false;
    }
  }, [onStartFailure, open, protocol, sessionId, unit]);

  const advanceSession = React.useCallback(async (overrideInputs) => {
    if (!unit || !sessionId) {
      return;
    }
    if (overrideInputs && typeof overrideInputs.preventDefault === "function") {
      overrideInputs = null;
    }
    setSessionLoading(true);
    setSessionError("");
    try {
      const inputs = overrideInputs ?? formatInputs(sessionStep, sessionValues);
      const response = await fetch(sessionAdvanceEndpoint(unit, sessionId), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ inputs }),
      });

      if (!response.ok) {
        let errorMessage = `Failed to advance session (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage = payload.error || payload.message || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      setSessionStep(payload.step);
      setSessionValues(buildInitialValues(payload.step));
    } catch (err) {
      setSessionError(err.message || "Failed to advance session.");
    } finally {
      setSessionLoading(false);
    }
  }, [sessionId, sessionStep, sessionValues, unit]);

  const abortSession = React.useCallback(
    async (shouldAbort) => {
      if (shouldAbort && sessionId && unit) {
        try {
          await fetch(sessionAbortEndpoint(unit, sessionId), {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
          });
          if (onAbortSuccess) {
            onAbortSuccess();
          }
        } catch (_error) {
          if (onAbortFailure) {
            onAbortFailure();
          }
        }
      }
      resetSessionState();
      if (onClose) {
        onClose();
      }
    },
    [onAbortFailure, onAbortSuccess, onClose, resetSessionState, sessionId, unit]
  );

  React.useEffect(() => {
    if (open) {
      startSession();
      return;
    }
    resetSessionState();
  }, [open, resetSessionState, startSession]);

  return (
    <Dialog
      open={open}
      onClose={(_event, reason) => {
        if (reason === "backdropClick") {
          return;
        }
        abortSession(!sessionResult);
      }}
      maxWidth="sm"
      fullWidth
      PaperProps={{ sx: { height: 600 } }}
    >
      <DialogTitle>
        {protocol?.title || "Calibration session"}
        <IconButton
          aria-label="close"
          onClick={() => abortSession(!sessionResult)}
          sx={{
            position: "absolute",
            right: 8,
            top: 8,
            color: (theme) => theme.palette.grey[500],
          }}
          size="large"
        >
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent
        sx={{
          display: "flex",
          flexDirection: "column",
          gap: 1,
          maxHeight: 520,
          overflowY: "auto",
        }}
      >
        <Box sx={{ height: 4, mb: 2 }}>
          <LinearProgress sx={{ visibility: sessionLoading ? "visible" : "hidden" }} />
        </Box>
        {sessionError && <Alert severity="error">{sessionError}</Alert>}
        {sessionStep ? (
          <Box sx={{mb: 1.5}}>
            <Typography variant="subtitle1" component="h2">
              {sessionStep.title || "Calibration step"}
            </Typography>
          </Box>
        ) : (
          <></>
        )}
        {stepImage && (
          <Box>
            <Box
              component="img"
              src={stepImage.src}
              alt={stepImage.alt || ""}
              sx={{
                width: "100%",
                maxHeight: 220,
                objectFit: "contain",
                borderRadius: 1,
                backgroundColor: "action.hover",
              }}
            />
            {stepImage.caption && (
              <Typography variant="caption" color="text.secondary">
                {stepImage.caption}
              </Typography>
            )}
          </Box>
        )}
        {chartPayload && (
          <Box>
            <CalibrationSessionChart chart={chartPayload} />
          </Box>
        )}
        {sessionStep && (
          <Typography variant="body2" sx={{ whiteSpace: "pre-line" }}>
            {sessionStep.body || "Follow the instructions for this step."}
          </Typography>
        )}
        <Box sx={{width: "75%", mt: 1}}>
          {sessionStep && Array.isArray(sessionStep.fields) && sessionStep.fields.length > 0 && (
            <Stack spacing={1}>
              {sessionStep.fields.map((field) => {
                if (
                  sessionStep.step_type === "action" &&
                  field.field_type === "bool" &&
                  field.name === "confirm"
                ) {
                  return null;
                }
                if (field.field_type === "bool" && field.name === "confirmed") {
                  return null;
                }
                if (field.field_type === "bool") {
                  return (
                    <FormControlLabel
                      key={field.name}
                      control={
                        <Switch
                          checked={Boolean(sessionValues[field.name])}
                          onChange={(event) =>
                            setSessionValues((prev) => ({
                              ...prev,
                              [field.name]: event.target.checked,
                            }))
                          }
                        />
                      }
                      label={field.label}
                    />
                  );
                }
                if (field.field_type === "choice") {
                  return (
                    <FormControl key={field.name} fullWidth size="small">
                      <FormLabel>{field.label}</FormLabel>
                      <Select
                        value={sessionValues[field.name] ?? ""}
                        onChange={(event) =>
                          setSessionValues((prev) => ({
                            ...prev,
                            [field.name]: event.target.value,
                          }))
                        }
                      >
                        {(field.options || []).map((option) => (
                          <MenuItem key={option} value={option}>
                            {option}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  );
                }
                const helperText =
                  field.field_type === "float_list" ? "Comma-separated values" : field.help_text;
                return (
                  <TextField
                    key={field.name}
                    fullWidth
                    size="small"
                    label={field.label}
                    value={sessionValues[field.name] ?? ""}
                    helperText={helperText || " "}
                    onChange={(event) =>
                      setSessionValues((prev) => ({
                        ...prev,
                        [field.name]: event.target.value,
                      }))
                    }
                  />
                );
              })}
            </Stack>
          )}
          {sessionResult?.calibrations && Array.isArray(sessionResult.calibrations) && unit && (
            <Stack spacing={1}>
              {sessionResult.calibrations.map((calibration) => (
                <Button
                  key={`${calibration.device}-${calibration.calibration_name}`}
                  component={Link}
                  to={`/calibrations/${unit}/${calibration.device}/${calibration.calibration_name}`}
                  sx={{ textTransform: "none", justifyContent: "flex-start" }}
                >
                  View calibration details ({calibration.device})
                </Button>
              ))}
            </Stack>
          )}
          {sessionResult?.calibration?.calibration_name &&
            !sessionResult?.calibrations &&
            unit && (
              <Button
                component={Link}
                to={`/calibrations/${unit}/${protocol?.device}/${sessionResult.calibration.calibration_name}`}
                sx={{ textTransform: "none" }}
              >
                View calibration details
              </Button>
            )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ justifyContent: "right", alignItems: "center" }}>
        {inlineActions.length > 0 ? (
          <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", pl: 1 }}>
            {inlineActions.map((action) => (
              <Button
                key={action.label}
                variant="text"
                onClick={() => advanceSession(action.inputs)}
                sx={{ textTransform: "none" }}
                disabled={sessionLoading}
              >
                {action.label}
              </Button>
            ))}
          </Stack>
        ) : (
          <span />
        )}
        {!sessionResult && (
          <Button
            onClick={() => abortSession(true)}
            color="secondary"
            sx={{ textTransform: "none" }}
          >
            Abort
          </Button>
        )}
        <Button
          variant="contained"
          onClick={sessionResult ? () => abortSession(false) : advanceSession}
          disabled={!sessionStep || sessionLoading}
          sx={{ textTransform: "none" }}
        >
          {sessionResult ? "Done" : "Continue"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
