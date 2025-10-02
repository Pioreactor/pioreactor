import React, { useState, useEffect } from "react";

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
  Snackbar,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import PioreactorIcon from "./PioreactorIcon";
import { runPioreactorJob } from "../utilities";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ReplayIcon from '@mui/icons-material/Replay';
import SettingsOutlinedIcon from '@mui/icons-material/SettingsOutlined';


function AdvancedConfigDialog({ open, onFinished, jobName, displayName, unit, experiment, config = {} }) {
  const [values, setValues] = useState({});              // local, editable copy
  const [original, setOriginal] = useState({});          // immutable reference
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  // Reset dialog state every time it is opened or config changes
  useEffect(() => {
    if (open) {
      setValues(config);
      setOriginal(config);
    }
  }, [open, config]);

  const handleClose = () => onFinished();

  const handleFieldChange = (param) => (e) => {
    setValues((prev) => ({ ...prev, [param]: e.target.value }));
  };

  const handleReset = (param) => () => {
    setValues((prev) => ({ ...prev, [param]: original[param] }));
  };

  const handleStart = (e) => {
    e.preventDefault();

    // Build a minimal overrides object: only send keys whose value changed
    const overrides = Object.fromEntries(
      Object.entries(values).filter(([k, v]) => original[k] !== v)
    );

    runPioreactorJob(unit, experiment, jobName, [], {}, overrides);

    setSnackbarOpen(true);
    handleClose();
  };

  return (
    <>
      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title" PaperProps={{style: {height: "100%"}}} fullWidth>
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
                  InputLabelProps={{ shrink: true }}
                  InputProps={{
                    endAdornment: isModified && (
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
                    ),
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
       <SettingsOutlinedIcon sx={{width: "21px", mb: 0.25, mr: .25}} /> Advanced
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
