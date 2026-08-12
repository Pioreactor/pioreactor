import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import IconButton from "@mui/material/IconButton";
import LinearProgress from "@mui/material/LinearProgress";
import Stack from "@mui/material/Stack";
import CloseIcon from "@mui/icons-material/Close";
import CalibrationSessionFields from "./CalibrationSessionFields";
import CalibrationSessionResultLinks from "./CalibrationSessionResultLinks";
import CalibrationSessionStepContent from "./CalibrationSessionStepContent";

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
      if (typeof field.default === "string") {
        nextValues[field.name] = field.default.toLowerCase() === "yes" ? "yes" : "no";
        return;
      }
      nextValues[field.name] = field.default ? "yes" : "no";
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
      if (typeof rawValue === "string") {
        output[field.name] = rawValue.toLowerCase() === "yes";
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
  sessionId: sessionIdProp,
  onSessionId,
  onComplete,
  onPause,
  onClose,
  onAbortSuccess,
  onAbortFailure,
  onStartFailure,
}) {
  const [sessionId, setSessionId] = React.useState(sessionIdProp ?? null);
  const [sessionStep, setSessionStep] = React.useState(null);
  const [sessionError, setSessionError] = React.useState("");
  const [sessionLoading, setSessionLoading] = React.useState(false);
  const [showLoading, setShowLoading] = React.useState(false);
  const [sessionValues, setSessionValues] = React.useState({});
  const [loadingImageIndex, setLoadingImageIndex] = React.useState(0);
  const [loadedStepImageSrc, setLoadedStepImageSrc] = React.useState(null);
  const [imageActionPending, setImageActionPending] = React.useState(false);
  const startInFlightRef = React.useRef(false);
  const loadingDelayTimerRef = React.useRef(null);
  const loadingImageTimerRef = React.useRef(null);

  const sessionResult = sessionStep?.result || sessionStep?.metadata?.result;
  const inlineActions = Array.isArray(sessionStep?.metadata?.actions)
    ? sessionStep.metadata.actions
    : [];
  const dialogPresentation = sessionStep?.metadata?.dialog;
  const loadingImages = Array.isArray(sessionStep?.metadata?.loading_images)
    ? sessionStep.metadata.loading_images
    : [];
  const primaryActionLabel =
    sessionResult ? "Done" : sessionStep?.metadata?.primary_action_label || "Continue";

  const resetSessionState = React.useCallback(() => {
    setSessionId(null);
    setSessionStep(null);
    setSessionError("");
    setSessionLoading(false);
    setSessionValues({});
    setLoadedStepImageSrc(null);
    setImageActionPending(false);
    startInFlightRef.current = false;
  }, []);

  React.useEffect(() => {
    if (sessionIdProp === undefined) {
      return;
    }
    setSessionId(sessionIdProp);
  }, [sessionIdProp]);

  const effectiveSessionId = sessionIdProp ?? sessionId;

  const updateSessionValue = React.useCallback((fieldName, value) => {
    setSessionValues((previousValues) => ({ ...previousValues, [fieldName]: value }));
  }, []);

  const startSession = React.useCallback(async () => {
    if (!open || !protocol || !unit) {
      return;
    }
    if (startInFlightRef.current || effectiveSessionId) {
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
          protocol_name: protocol.protocol_name,
          target_device: protocol.target_device,
        }),
      });

      if (!response.ok) {
        let errorMessage = `Failed to start session (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage = payload.error || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }

      const payload = await response.json();
      const nextSessionId = payload.session?.session_id;
      setSessionId(nextSessionId);
      if (nextSessionId && onSessionId) {
        onSessionId(nextSessionId);
      }
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
  }, [effectiveSessionId, onSessionId, onStartFailure, open, protocol, unit]);

  const loadSession = React.useCallback(async () => {
    if (!open || !unit || !effectiveSessionId) {
      return;
    }
    setSessionLoading(true);
    setSessionError("");
    try {
      const response = await fetch(`/api/workers/${unit}/calibrations/sessions/${effectiveSessionId}`);
      if (!response.ok) {
        throw new Error(`Failed to load session (${response.status}).`);
      }
      const payload = await response.json();
      if (payload.step) {
        setSessionStep(payload.step);
        setSessionValues(buildInitialValues(payload.step));
      } else {
        setSessionStep(null);
        setSessionValues({});
      }
    } catch (err) {
      setSessionError(err.message || "Failed to load session.");
    } finally {
      setSessionLoading(false);
    }
  }, [effectiveSessionId, open, unit]);

  const advanceSession = React.useCallback(async (overrideInputs, imageUpdateExpected) => {
    if (!unit || !effectiveSessionId) {
      return;
    }
    if (overrideInputs && typeof overrideInputs.preventDefault === "function") {
      overrideInputs = null;
    }
    setSessionLoading(true);
    setImageActionPending(imageUpdateExpected === true);
    setSessionError("");
    try {
      const inputs = overrideInputs ?? formatInputs(sessionStep, sessionValues);
      const response = await fetch(sessionAdvanceEndpoint(unit, effectiveSessionId), {
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
          errorMessage = payload.error || JSON.stringify(payload);
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
      setImageActionPending(false);
      setSessionLoading(false);
    }
  }, [effectiveSessionId, sessionStep, sessionValues, unit]);

  const abortSession = React.useCallback(
    async (shouldAbort) => {
      if (shouldAbort && effectiveSessionId && unit) {
        try {
          const response = await fetch(sessionAbortEndpoint(unit, effectiveSessionId), {
            method: "POST",
            headers: {
              Accept: "application/json",
              "Content-Type": "application/json",
            },
          });
          if (!response.ok) {
            let errorMessage = `Failed to abort calibration session (${response.status}).`;
            try {
              const payload = await response.json();
              errorMessage = payload.error || JSON.stringify(payload);
            } catch (_error) {
              // Keep the fallback message.
            }
            throw new Error(errorMessage);
          }
          if (onAbortSuccess) {
            onAbortSuccess();
          }
        } catch (err) {
          const message = err.message || "Failed to abort calibration session.";
          setSessionError(message);
          if (onAbortFailure) {
            onAbortFailure(message);
          }
          return;
        }
      }
      if (!shouldAbort && onComplete) {
        onComplete();
      }
      resetSessionState();
      if (onClose) {
        onClose();
      }
    },
    [effectiveSessionId, onAbortFailure, onAbortSuccess, onClose, onComplete, resetSessionState, unit]
  );

  React.useEffect(() => {
    if (!open) {
      if (!effectiveSessionId) {
        resetSessionState();
      }
      return;
    }
    if (effectiveSessionId) {
      loadSession();
      return;
    }
    startSession();
  }, [effectiveSessionId, loadSession, open, resetSessionState, startSession]);

  React.useEffect(() => {
    if (!sessionLoading) {
      if (loadingDelayTimerRef.current) {
        clearTimeout(loadingDelayTimerRef.current);
        loadingDelayTimerRef.current = null;
      }
      setShowLoading(false);
      if (loadingImageTimerRef.current) {
        clearInterval(loadingImageTimerRef.current);
        loadingImageTimerRef.current = null;
      }
      setLoadingImageIndex(0);
      return;
    }
    if (loadingDelayTimerRef.current) {
      return;
    }
    loadingDelayTimerRef.current = setTimeout(() => {
      loadingDelayTimerRef.current = null;
      setShowLoading(true);
    }, 250);
  }, [sessionLoading]);

  React.useEffect(() => {
    if (!showLoading || loadingImages.length === 0) {
      if (loadingImageTimerRef.current) {
        clearInterval(loadingImageTimerRef.current);
        loadingImageTimerRef.current = null;
      }
      setLoadingImageIndex(0);
      return;
    }
    if (loadingImages.length === 1) {
      setLoadingImageIndex(0);
      return;
    }
    if (loadingImageTimerRef.current) {
      return;
    }
    loadingImageTimerRef.current = setInterval(() => {
      setLoadingImageIndex((prev) => (prev + 1) % loadingImages.length);
    }, 45);
    return () => {
      if (loadingImageTimerRef.current) {
        clearInterval(loadingImageTimerRef.current);
        loadingImageTimerRef.current = null;
      }
    };
  }, [showLoading, loadingImages.length]);

  return (
    <Dialog
      open={open}
      onClose={(_event, reason) => {
        if (sessionResult) {
          abortSession(false);
          return;
        }
        if (
          (reason === "backdropClick" || reason === "escapeKeyDown") &&
          !sessionResult &&
          onPause
        ) {
          onPause();
        }
        if (onClose) {
          onClose();
        }
      }}
      maxWidth={dialogPresentation?.max_width || "sm"}
      fullWidth
      slotProps={{
        paper: {
          sx: {
            height: dialogPresentation?.height || 620,
          },
        },
      }}
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
          overflowY: "auto",
        }}
      >
        <Box sx={{ height: 4, mb: 2 }}>
          <LinearProgress sx={{ visibility: showLoading ? "visible" : "hidden" }} />
        </Box>
        {sessionError && <Alert severity="error">{sessionError}</Alert>}
        {sessionResult && (
          <Box
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 1,
              mb: 1,
            }}
          >
            <Box
              component="img"
              src="/static/svgs/calibration-complete.svg"
              alt="Calibration complete"
              sx={{ width: 150, height: 150 }}
            />
          </Box>
        )}
        <CalibrationSessionStepContent
          step={sessionStep}
          showLoading={showLoading}
          loadingImages={loadingImages}
          loadingImageIndex={loadingImageIndex}
          loadedStepImageSrc={loadedStepImageSrc}
          imageActionPending={imageActionPending}
          onStepImageLoad={setLoadedStepImageSrc}
          onStepImageError={(imageSrc) => {
            setLoadedStepImageSrc(imageSrc);
            setSessionError("Image could not be loaded. Try again.");
          }}
        />
        <Box sx={{ width: "75%", mt: 1 }}>
          <CalibrationSessionFields
            step={sessionStep}
            values={sessionValues}
            onFieldChange={updateSessionValue}
          />
          <CalibrationSessionResultLinks
            result={sessionResult}
            protocolTargetDevice={protocol?.target_device}
            unit={unit}
          />
        </Box>
      </DialogContent>
      <DialogActions sx={{ justifyContent: "right", alignItems: "center" }}>
        {inlineActions.length > 0 && (
          <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", pl: 1 }}>
            {inlineActions.map((action) => (
              <Button
                key={action.label}
                variant="text"
                onClick={() => advanceSession(action.inputs, action.updates_image === true)}
                sx={{ textTransform: "none" }}
                disabled={sessionLoading}
              >
                {action.label}
              </Button>
            ))}
          </Stack>
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
          {primaryActionLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
