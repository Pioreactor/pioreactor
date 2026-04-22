import React from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import LinearProgress from "@mui/material/LinearProgress";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import TuneIcon from "@mui/icons-material/Tune";
import { Link as RouterLink } from "react-router";

function getBatchProgress(batch) {
  const rows = Object.values(batch?.units || {});
  if (rows.length === 0) {
    return 0;
  }
  const finishedCount = rows.filter((row) => ["completed", "failed", "aborted"].includes(row.status)).length;
  return (finishedCount / rows.length) * 100;
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

  React.useEffect(() => {
    if (!open) {
      setBatch(null);
      setBatchError("");
      setIsStarting(false);
      setIsAborting(false);
    }
  }, [open]);

  React.useEffect(() => {
    if (!open || !batch?.batch_id) {
      return;
    }
    if (!["pending", "running"].includes(batch.status)) {
      return;
    }

    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await fetch(`/api/calibration_batches/stirring/${batch.batch_id}`);
        if (!response.ok) {
          throw new Error(`Failed to load stirring batch (${response.status}).`);
        }
        const payload = await response.json();
        setBatch(payload.batch);
      } catch (err) {
        setBatchError(err.message || "Failed to load stirring batch.");
      }
    }, 1000);

    return () => window.clearTimeout(timeoutId);
  }, [batch, open]);

  const handleStart = async () => {
    setIsStarting(true);
    setBatchError("");
    try {
      const response = await fetch("/api/calibration_batches/stirring", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ units }),
      });
      if (!response.ok) {
        let errorMessage = `Failed to start stirring calibration batch (${response.status}).`;
        try {
          const payload = await response.json();
          errorMessage = payload.error || JSON.stringify(payload);
        } catch (_error) {
          // Keep the fallback message.
        }
        throw new Error(errorMessage);
      }
      const payload = await response.json();
      setBatch(payload.batch);
    } catch (err) {
      setBatchError(err.message || "Failed to start stirring calibration batch.");
    } finally {
      setIsStarting(false);
    }
  };

  const handleAbort = async () => {
    if (!batch?.batch_id) {
      return;
    }
    setIsAborting(true);
    setBatchError("");
    try {
      const response = await fetch(`/api/calibration_batches/stirring/${batch.batch_id}/abort`, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
      });
      if (!response.ok) {
        throw new Error(`Failed to abort stirring batch (${response.status}).`);
      }
      const payload = await response.json();
      setBatch(payload.batch);
    } catch (err) {
      setBatchError(err.message || "Failed to abort stirring batch.");
    } finally {
      setIsAborting(false);
    }
  };

  const progress = getBatchProgress(batch);
  const isRunning = batch && ["pending", "running"].includes(batch.status);
  const isComplete = batch?.status === "complete";

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{protocol?.title || "Stirring calibration batch"}</DialogTitle>
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
            <Typography variant="subtitle2">Units</Typography>
            <Box component="ul" sx={{ mt: 0, mb: 0, pl: 3 }}>
              {units.map((unit) => (
                <li key={unit}>
                  <Typography variant="body2">{unit}</Typography>
                </li>
              ))}
            </Box>
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
                {units.length} units selected
              </Typography>
              <LinearProgress variant="determinate" value={progress} />
            </Box>

            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Pioreactor</TableCell>
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
        <Button onClick={onClose} sx={{ textTransform: "none" }}>
          {batch?.status === "complete" ? "Done" : "Close"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
