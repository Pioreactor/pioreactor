import React, { useRef, useState } from "react";
import { Alert, Box, Button, Checkbox, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle, Table, TableBody, TableCell, TableContainer, TableHead, TableRow, TextField, Typography } from "@mui/material";
import EditIcon from "@mui/icons-material/EditOutlined";
import SaveIcon from "@mui/icons-material/Save";
import DialogCloseButton from "./DialogCloseButton";
import { ZebraTableRow } from "./TableRows";
import { textIcon } from "../theme";
import { calibrationAxisPrecision, formatCalibrationNumber } from "../utils/formatCalibrationNumber";
import { fetchTaskResult, getUnitTaskResult } from "../utils/tasks";

function measurementValueError(value) {
  if (String(value).trim() === "") return "Required";
  if (!Number.isFinite(Number(value))) return "Enter a number";
  return "";
}

function MeasurementInput({ value, label, precision, disabled, onChange }) {
  const [focused, setFocused] = useState(false);
  const error = measurementValueError(value);
  return (
    <TextField
      size="small"
      value={focused || error ? value : formatCalibrationNumber(Number(value), precision)}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      onChange={(event) => onChange(event.target.value)}
      disabled={disabled}
      error={Boolean(error)}
      helperText={error || undefined}
      slotProps={{ htmlInput: { "aria-label": label, inputMode: "decimal", style: { textAlign: "right" } } }}
      sx={{ width: 140 }}
    />
  );
}

function MeasurementsTable({ calibration, included, onChange, yValues, onValueChange, saving = false }) {
  const { x, y, recorded_data: data } = calibration;
  const MeasurementRow = onChange ? ZebraTableRow : TableRow;
  const alignment = onChange ? "right" : "left";
  return (
    <TableContainer sx={{ maxHeight: 300 }}>
      <Table size="small" stickyHeader={Boolean(onChange)}>
        <TableHead>
          <TableRow>
            {onChange && <TableCell>Include</TableCell>}
            <TableCell align={alignment}>{x.toLowerCase() === "voltage" ? "Voltage (V)" : x}</TableCell>
            <TableCell align={alignment}>{y.toLowerCase() === "voltage" ? "Voltage (V)" : y}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {data.x.map((xValue, index) => (
            <MeasurementRow
              key={index}
              sx={!onChange && !included[index] ? { "& .MuiTableCell-root": { color: "text.disabled" } } : undefined}
            >
              {onChange && (
                <TableCell padding="checkbox">
                  <Checkbox
                    checked={included[index]}
                    disabled={saving}
                    slotProps={{ input: { "aria-label": `Include measurement ${index + 1}` } }}
                    onChange={(_event, checked) => onChange(index, checked)}
                  />
                </TableCell>
              )}
              <TableCell align={alignment}>
                {formatCalibrationNumber(xValue, calibrationAxisPrecision(x))}
              </TableCell>
              <TableCell align={alignment}>
                {onValueChange ? (
                  <MeasurementInput
                    value={yValues[index]}
                    label={`${y} for measurement ${index + 1}`}
                    precision={calibrationAxisPrecision(y)}
                    disabled={saving}
                    onChange={(nextValue) => onValueChange(index, nextValue)}
                  />
                ) : formatCalibrationNumber(data.y[index], calibrationAxisPrecision(y))}
              </TableCell>
            </MeasurementRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

export default function CalibrationMeasurements({ calibration, unit, device, name, onSaved }) {
  const [draft, setDraft] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const savedMask = calibration.included ?? calibration.recorded_data.x.map(() => true);
  const included = draft?.included ?? savedMask;
  const savedValues = calibration.recorded_data.y;
  const yValues = draft?.yValues ?? savedValues;
  const valuesChanged = yValues.some((value, index) => Number(value) !== savedValues[index]);
  const invalidValues = yValues.some((value) => measurementValueError(value));
  const dirty = valuesChanged || included.some((value, index) => value !== savedMask[index]);

  const close = () => {
    if (pending.current) return;
    setDraft(null);
    setError("");
  };

  const save = async () => {
    if (pending.current || invalidValues) return;
    pending.current = true;
    setSaving(true);
    setError("");
    try {
      const result = await fetchTaskResult(
        `/api/workers/${unit}/calibrations/${device}/${encodeURIComponent(name)}`,
        {
          fetchOptions: {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ included, ...(valuesChanged ? { y_values: yValues.map(Number) } : {}) }),
          },
          maxRetries: 400,
        },
      );
      const saved = getUnitTaskResult(result, unit, "Unable to save calibration measurements.");
      onSaved(saved);
      setDraft(null);
    } catch (err) {
      setError(err.message || "Unable to save calibration measurements. Try again.");
    } finally {
      pending.current = false;
      setSaving(false);
    }
  };

  return (
    <Box sx={{ px: 5, mt: 5 }}>
      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
        <Typography variant="h6" component="h2">Recorded data</Typography>
        <Button onClick={() => { setDraft({ included: [...savedMask], yValues: savedValues.map(String) }); setError(""); }}>
          <EditIcon fontSize="small" sx={textIcon} /> Edit
        </Button>
      </Box>
      <MeasurementsTable calibration={calibration} included={savedMask} />
      <Dialog open={draft !== null} onClose={close} fullWidth maxWidth="sm" aria-labelledby="edit-calibration-measurements-title">
        <DialogTitle id="edit-calibration-measurements-title" sx={{ pr: 6 }}>
          Edit recorded data
          <DialogCloseButton onClick={close} disabled={saving} />
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Edit {calibration.y} values or choose which measurements to include in the curve.
          </Typography>
          <MeasurementsTable
            calibration={calibration}
            included={included}
            saving={saving}
            yValues={yValues}
            onValueChange={(index, value) => {
              setDraft({ ...draft, yValues: yValues.map((current, i) => i === index ? value : current) });
              setError("");
            }}
            onChange={(index, checked) => {
              setDraft({ ...draft, included: included.map((current, i) => i === index ? checked : current) });
              setError("");
            }}
          />
          {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        </DialogContent>
        <DialogActions>
          <Button disabled={saving} color="secondary" onClick={close}>Cancel</Button>
          <Button
            variant="contained"
            disabled={!dirty || saving || invalidValues}
            onClick={save}
            endIcon={saving ? <CircularProgress size={18} color="inherit" /> : <SaveIcon />}
          >
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
