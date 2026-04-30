import React, { useState, useEffect, useRef } from "react";

import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  TextField,
  IconButton,
  InputAdornment,
  FormControl,
  FormLabel,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import PioreactorIcon from "./PioreactorIcon";
import { runPioreactorJob } from "../utils/jobs";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ReplayIcon from '@mui/icons-material/Replay';
import Snackbar from './Snackbar';


function AdvancedConfigDialog({ open, onFinished, jobName, displayName, unit, experiment, config = {} }) {
  const [values, setValues] = useState({});              // local, editable copy
  const [original, setOriginal] = useState({});          // immutable reference
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const userEditedRef = useRef(false);

  // Reset dialog state every time it is opened. The parent (Pioreactor.jsx)
  // fetches `/api/config/units/${unit}` once on mount and never refreshes,
  // so the `config` prop may be stale relative to disk — for example after a
  // job's own persistence step writes back its current settings on Stop.
  //
  // Strategy: seed from the prop synchronously so the dialog renders populated
  // immediately, then re-fetch in the background and overwrite if the API
  // returns fresher data. On fetch error the optimistic seed already supplied
  // a usable form.
  useEffect(() => {
    if (!open) return;

    userEditedRef.current = false;
    setValues(config);
    setOriginal(config);

    let cancelled = false;
    fetch(`/api/config/units/${unit}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (cancelled) return;
        const fresh = data?.[unit]?.[`${jobName}.config`];
        if (fresh !== undefined) {
          setOriginal(fresh);
          if (!userEditedRef.current) {
            setValues(fresh);
          }
        }
      })
      .catch(() => { /* optimistic seed already populated the form */ });

    return () => { cancelled = true; };
  }, [open, unit, jobName, config]);

  const handleClose = () => onFinished();

  const handleFieldChange = (param) => (e) => {
    userEditedRef.current = true;
    setValues((prev) => ({ ...prev, [param]: e.target.value }));
  };

  const handleReset = (param) => () => {
    setValues((prev) => ({ ...prev, [param]: original[param] }));
  };

  const handleStart = (e) => {
    e.preventDefault();

    // Build section-aware overrides: [section, key, value]
    const overrides = Object.entries(values)
      .filter(([k, v]) => original[k] !== v)
      .map(([parameter, value]) => [`${jobName}.config`, parameter, value]);

    runPioreactorJob(unit, experiment, jobName, [], {}, overrides);

    setSnackbarOpen(true);
    handleClose();
  };

  return (
    <>
      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title" slotProps={{ paper: { sx: { height: "100%" } } }} fullWidth>
        <DialogTitle >
          <Typography sx={{ fontSize: 13, color: "rgba(0,0,0,0.60)" }}>
            <PioreactorIcon sx={{ fontSize: "1.2em", verticalAlign: "middle" }} /> {unit}
          </Typography>
          <Typography sx={{ fontSize: 20, color: "rgba(0,0,0,0.87)" }}>
            {displayName}
          </Typography>
          <IconButton
            aria-label="close"
            onClick={handleClose}
            sx={{ position: "absolute", right: 8, top: 8, color: (theme) => theme.palette.grey[500] }}
            size="large"
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>

        <DialogContent >
          {Object.keys(values).length === 0 && (
            <Typography variant="body2" component="p" color="textSecondary">No configuration parameters found for {jobName}.</Typography>
          )}

          {Object.keys(values).length > 0 && ( <Typography variant="body2" component="span" gutterBottom>
            Override your default configuration parameters from section <code>[{jobName +".config"}]</code>. These changes only apply to this run.
          </Typography>
          )}
          <form>
          <FormControl component="fieldset" sx={{mt: 2}}>
          <FormLabel component="legend">Configuration</FormLabel>
            <div>
            {Object.entries(values).map(([param, value]) => {
              const isModified = original[param] !== value;
              return (
                <TextField
                  key={param}
                  label={param}
                  size="small"
                  autoComplete="off"
                  variant="outlined"
                  value={value}
                  onChange={handleFieldChange(param)}
                  slotProps={{
                    inputLabel: { shrink: true },
                    input: {
                      endAdornment: isModified ? (
                        <InputAdornment position="end">
                          <IconButton
                            size="small"
                            aria-label={`Reset ${param}`}
                            onClick={handleReset(param)}
                          >
                            <ReplayIcon
                              sx={{ color: (theme) => theme.palette.warning.main }}
                              fontSize="small"
                            />
                          </IconButton>
                        </InputAdornment>
                      ) : undefined,
                    },
                  }}
                  sx={{ mt: 2, mr: 2, mb: 0, width: "25ch" }}
                />
              );
            })}
            </div>
          </FormControl>
          </form>
        </DialogContent>

        <DialogActions>
          <Button color="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleStart} disabled={Object.keys(values).length === 0}>
            Start
          </Button>
        </DialogActions>
      </Dialog>

      {/* Feedback snackbar */}
      <Snackbar
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        open={snackbarOpen}
        onClose={() => setSnackbarOpen(false)}
        message={`Starting ${jobName} with configuration overrides.`}
        autoHideDuration={7000}
      />
    </>
  );
}

export default function AdvancedConfigButton({ jobName, displayName, unit, experiment, config, disabled }) {
  const [open, setOpen] = useState(false);

  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  return (
    <>
      <Button  size="small" variant="text" disabled={disabled} onClick={handleOpen} style={{textTransform: 'none', float: "right", marginRight: "0px"}}>
       <ExpandMoreIcon sx={{width: "21px", mb: 0.25, mr: .25}} /> Advanced
      </Button>
      <AdvancedConfigDialog
        open={open}
        onFinished={handleClose}
        jobName={jobName}
        unit={unit}
        experiment={experiment}
        config={config}
        displayName={displayName}
      />
    </>
  );
}
