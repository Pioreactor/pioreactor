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
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ReplayIcon from '@mui/icons-material/Replay';

import PioreactorIcon from "./PioreactorIcon";
import ChangeAutomationsDialog from "./ChangeAutomationsDialog";
import ChangeDosingAutomationsDialog from "./ChangeDosingAutomationsDialog";

export default function AutomationAdvancedConfigButton({
  jobName,              // ex: "temperature_automation"
  displayName,          // ex: "Temperature automation"
  automationType,       // one of: "temperature" | "led" | "dosing"
  unit,
  experiment,
  label,
  config = {},          // values from [jobName.config]
  disabled = false,
  // Dosing extras for ChangeDosingAutomationsDialog
  maxVolume,
  liquidVolume,
  threshold,
  no_skip_first_run = false,
}) {
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({});
  const [original, setOriginal] = useState({});
  const [openChangeDialog, setOpenChangeDialog] = useState(false);
  const [configOverrides, setConfigOverrides] = useState({});

  useEffect(() => {
    if (open) {
      setValues(config || {});
      setOriginal(config || {});
    }
  }, [open, config]);

  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const handleFieldChange = (param) => (e) => {
    setValues((prev) => ({ ...prev, [param]: e.target.value }));
  };

  const handleReset = (param) => () => {
    setValues((prev) => ({ ...prev, [param]: original[param] }));
  };

  const handleStartToAutomationDialog = (e) => {
    e.preventDefault();
    const overrides = Object.fromEntries(
      Object.entries(values).filter(([k, v]) => original[k] !== v)
    );
    setConfigOverrides(overrides);
    setOpen(false);
    setOpenChangeDialog(true);
  };

  return (
    <>
      <Button size="small" variant="text" disabled={disabled} onClick={handleOpen} style={{textTransform: 'none', float: "right", marginRight: 0}}>
        <ExpandMoreIcon sx={{width: 21, mb: 0.25, mr: .25}} /> Advanced
      </Button>

      <Dialog open={open} onClose={handleClose} aria-labelledby="form-dialog-title" PaperProps={{style: {height: "100%"}}} fullWidth>
        <DialogTitle>
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

        <DialogContent>
          {Object.keys(values || {}).length === 0 && (
            <Typography variant="body2" component="p" color="textSecondary">No configuration parameters found for {jobName}.</Typography>
          )}

          {Object.keys(values || {}).length > 0 && (
            <Typography variant="body2" component="span" gutterBottom>
              Override your default configuration parameters from section <code>[{jobName + ".config"}]</code>. These changes only apply to this run.
            </Typography>
          )}

          <form>
            <FormControl component="fieldset" sx={{ mt: 2 }}>
              <FormLabel component="legend">Configuration</FormLabel>
              <div>
                {Object.entries(values || {}).map(([param, value]) => {
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
                            <IconButton size="small" aria-label={`Reset ${param}`} onClick={handleReset(param)}>
                              <ReplayIcon sx={{ color: (theme) => theme.palette.warning.main }} fontSize="small" />
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
          <Button variant="contained" onClick={handleStartToAutomationDialog} disabled={Object.keys(values || {}).length === 0}>
            Next
          </Button>
        </DialogActions>
      </Dialog>

      {automationType === "dosing" ? (
        <ChangeDosingAutomationsDialog
          open={openChangeDialog}
          onFinished={() => setOpenChangeDialog(false)}
          unit={unit}
          label={label}
          experiment={experiment}
          no_skip_first_run={false}
          maxVolume={maxVolume}
          liquidVolume={liquidVolume}
          threshold={threshold}
          configOverrides={configOverrides}
        />
      ) : (
        <ChangeAutomationsDialog
          automationType={automationType}
          open={openChangeDialog}
          onFinished={() => setOpenChangeDialog(false)}
          unit={unit}
          label={label}
          experiment={experiment}
          no_skip_first_run={no_skip_first_run}
          configOverrides={configOverrides}
        />
      )}
    </>
  );
}
