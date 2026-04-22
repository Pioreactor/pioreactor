import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControl from "@mui/material/FormControl";
import FormGroup from "@mui/material/FormGroup";
import FormLabel from "@mui/material/FormLabel";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import TuneIcon from "@mui/icons-material/Tune";
import { Link as RouterLink } from "react-router";

const START_SESSION_ENDPOINT = (unit) => `/api/workers/${unit}/calibrations/sessions`;
const ADVANCE_SESSION_ENDPOINT = (unit, sessionId) =>
  `/api/workers/${unit}/calibrations/sessions/${sessionId}/inputs`;
const ABORT_SESSION_ENDPOINT = (unit, sessionId) =>
  `/api/workers/${unit}/calibrations/sessions/${sessionId}/abort`;

function createPendingBatch(units) {
  return {
    status: "pending",
    units: Object.fromEntries(units.map((unit) => [unit, { status: "pending" }])),
  };
}

function getBatchProgress(batch) {
  const rows = Object.values(batch?.units || {});
  if (rows.length === 0) {
    return 0;
  }
  const finishedCount = rows.filter((row) => ["completed", "failed", "aborted"].includes(row.status)).length;
  return (finishedCount / rows.length) * 100;
}

function getStepResult(step) {
  if (!step || typeof step !== "object") {
    return null;
  }
  if (step.result && typeof step.result === "object") {
    return step.result;
  }
  if (step.metadata?.result && typeof step.metadata.result === "object") {
    return step.metadata.result;
  }
  return null;
}

function renderCalibrationLinks(unit, result) {
  const calibrations = Array.isArray(result?.calibrations)
    ? result.calibrations
    : result?.calibration
      ? [result.calibration]
      : [];

  if (calibrations.length === 0) {
    return "—";
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5 }}>
      {calibrations.map((calibration) => (
        <Chip
          key={`${unit}-${calibration.device}-${calibration.calibration_name}`}
          size="small"
          icon={<TuneIcon />}
          clickable
          component={RouterLink}
          to={`/calibrations/${unit}/${calibration.device}/${calibration.calibration_name}`}
          label={calibration.calibration_name}
        />
      ))}
    </Box>
  );
}

async function responseToJson(response, fallbackMessage) {
  if (!response.ok) {
    let errorMessage = fallbackMessage;
    try {
      const payload = await response.json();
      errorMessage = payload.error || JSON.stringify(payload);
    } catch (_error) {
      // Keep the fallback message.
    }
    throw new Error(errorMessage);
  }
  return response.json();
}

async function abortSession(unit, sessionId) {
  await fetch(ABORT_SESSION_ENDPOINT(unit, sessionId), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
  });
}

export default function StirringCalibrationBatchDialog({
  open,
  protocol,
  units,
  onClose,
}) {
  const [batch, setBatch] = React.useState(null);
  const [batchError, setBatchError] = React.useState("");
  const [isStarting, setIsStarting] = React.useState(false);
  const [isAborting, setIsAborting] = React.useState(false);
  const abortRequestedRef = React.useRef(false);
  const runIdRef = React.useRef(0);

  const updateBatchUnit = React.useCallback((unit, updater) => {
    setBatch((previousBatch) => {
      if (!previousBatch) {
        return previousBatch;
      }
      return {
        ...previousBatch,
        units: {
          ...previousBatch.units,
          [unit]: updater(previousBatch.units[unit] || { status: "pending" }),
        },
      };
    });
  }, []);

  const markBatchStatus = React.useCallback((status) => {
    setBatch((previousBatch) => {
      if (!previousBatch) {
        return previousBatch;
      }
      return { ...previousBatch, status };
    });
  }, []);

  const abortKnownSessions = React.useCallback(async () => {
    const sessionEntries = Object.entries(batch?.units || {})
      .map(([unit, details]) => [unit, details?.session_id])
      .filter(([, sessionId]) => Boolean(sessionId));

    await Promise.allSettled(
      sessionEntries.map(([unit, sessionId]) => abortSession(unit, sessionId)),
    );
  }, [batch]);

  React.useEffect(() => {
    if (!open) {
      abortRequestedRef.current = false;
      setBatch(null);
      setBatchError("");
      setIsStarting(false);
      setIsAborting(false);
    }
  }, [open]);

  const runCalibrationForUnit = React.useCallback(async (unit, runId) => {
    const startPayload = await fetch(START_SESSION_ENDPOINT(unit), {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        protocol_name: protocol.protocol_name,
        target_device: protocol.target_device,
      }),
    }).then((response) => responseToJson(response, `Failed to start stirring session for ${unit}.`));

    const sessionId = startPayload.session?.session_id;
    if (!sessionId) {
      throw new Error(`Unit ${unit} started without a session id.`);
    }

    if (abortRequestedRef.current || runId !== runIdRef.current) {
      await abortSession(unit, sessionId);
      return;
    }

    updateBatchUnit(unit, (details) => ({
      ...details,
      status: "running",
      session_id: sessionId,
      error: undefined,
    }));

    const advance = async (message) =>
      fetch(ADVANCE_SESSION_ENDPOINT(unit, sessionId), {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ inputs: {} }),
      }).then((response) => responseToJson(response, message));

    await advance(`Failed to advance stirring session for ${unit}.`);
    if (abortRequestedRef.current || runId !== runIdRef.current) {
      await abortSession(unit, sessionId);
      return;
    }

    const finalPayload = await advance(`Failed to finish stirring session for ${unit}.`);
    if (abortRequestedRef.current || runId !== runIdRef.current) {
      await abortSession(unit, sessionId);
      return;
    }

    updateBatchUnit(unit, (details) => ({
      ...details,
      status: "completed",
      session_id: sessionId,
      result: getStepResult(finalPayload.step),
      error: undefined,
    }));
  }, [protocol, updateBatchUnit]);

  const handleStart = async () => {
    const runId = runIdRef.current + 1;
    runIdRef.current = runId;
    abortRequestedRef.current = false;
    setIsStarting(true);
    setBatchError("");
    setBatch({
      ...createPendingBatch(units),
      status: "running",
    });

    try {
      await Promise.all(
        units.map(async (unit) => {
          try {
            await runCalibrationForUnit(unit, runId);
          } catch (error) {
            if (abortRequestedRef.current || runId !== runIdRef.current) {
              return;
            }
            updateBatchUnit(unit, (details) => ({
              ...details,
              status: "failed",
              error: error.message || `Failed to calibrate ${unit}.`,
            }));
          }
        }),
      );

      if (!abortRequestedRef.current && runId === runIdRef.current) {
        markBatchStatus("complete");
      }
    } finally {
      if (runId === runIdRef.current) {
        setIsStarting(false);
      }
    }
  };

  const handleAbort = async () => {
    abortRequestedRef.current = true;
    setIsAborting(true);
    setBatchError("");
    setBatch((previousBatch) => {
      if (!previousBatch) {
        return previousBatch;
      }

      const nextUnits = Object.fromEntries(
        Object.entries(previousBatch.units).map(([unit, details]) => [
          unit,
          ["completed", "failed"].includes(details.status)
            ? details
            : { ...details, status: "aborted", error: undefined },
        ]),
      );

      return {
        ...previousBatch,
        status: "aborted",
        units: nextUnits,
      };
    });

    try {
      await abortKnownSessions();
    } catch (error) {
      setBatchError(error.message || "Failed to abort stirring batch.");
    } finally {
      setIsStarting(false);
      setIsAborting(false);
    }
  };

  const progress = getBatchProgress(batch);
  const isRunning = batch && batch.status === "running";
  const isComplete = batch?.status === "complete";

  return (
    <Dialog
      open={open}
      onClose={(_event, reason) => {
        if ((reason === "backdropClick" || reason === "escapeKeyDown") && (isStarting || isRunning || isAborting)) {
          return;
        }
        onClose();
      }}
      maxWidth="sm"
      fullWidth
    >
      <DialogTitle>{protocol?.title}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 2 }}>
        {batchError && <Alert severity="error">{batchError}</Alert>}

        {!batch && (
          <React.Fragment>
            <Box
              component="img"
              src="/static/svgs/prepare-vial-arrow-pioreactor.svg"
              alt="Insert a vial with a stir bar and the liquid volume you plan to use."
              sx={{
                width: "100%",
                maxHeight: 220,
                objectFit: "contain",
                borderRadius: 1,
                backgroundColor: "action.hover",
              }}
            />
            <Typography variant="body2">
              Run the DC-based stirring calibration on all selected Pioreactors.
            </Typography>
            <Typography variant="body2">
              Each Pioreactor should have a vial with a stir bar and the liquid volume you plan to use.
              Stirring must be off before starting.
            </Typography>
            <FormControl component="fieldset" variant="standard">
              <FormLabel component="legend">Pioreactors</FormLabel>
              <FormGroup
                sx={
                  units.length > 8
                    ? {
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        columnGap: "30px",
                      }
                    : {}
                }
              >
                {units.map((unit) => (
                  <Typography
                    key={unit}
                    variant="body1"
                    sx={{ mt: 0.5 }}
                  >
                    {unit}
                  </Typography>
                ))}
              </FormGroup>
            </FormControl>
          </React.Fragment>
        )}

        {batch && (
          <React.Fragment>
            {isComplete && (
              <Box sx={{ display: "flex", justifyContent: "center" }}>
                <Box
                  component="img"
                  src="/static/svgs/calibration-complete.svg"
                  alt="Calibration complete"
                  sx={{ width: 150, height: 150 }}
                />
              </Box>
            )}
            <Box>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {units.length} Pioreactors selected
              </Typography>
              <LinearProgress variant="determinate" value={progress} />
            </Box>

            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Pioreactors</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Calibration</TableCell>
                    <TableCell>Error</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(batch.units).map(([unit, details]) => (
                    <TableRow key={unit}>
                      <TableCell>{unit}</TableCell>
                      <TableCell>{details.status}</TableCell>
                      <TableCell>{renderCalibrationLinks(unit, details.result)}</TableCell>
                      <TableCell>{details.error || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </React.Fragment>
        )}
      </DialogContent>
      <DialogActions>
        {isRunning && (
          <Button onClick={handleAbort} color="secondary" disabled={isAborting} sx={{ textTransform: "none" }}>
            Abort
          </Button>
        )}
        {!batch && (
          <Button onClick={handleStart} variant="contained" disabled={isStarting} sx={{ textTransform: "none" }}>
            Continue
          </Button>
        )}
        <Button
          onClick={onClose}
          disabled={isStarting || isRunning || isAborting}
          sx={{ textTransform: "none" }}
        >
          {batch?.status === "complete" ? "Done" : "Close"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
