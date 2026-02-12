import React, { useState, useEffect, useMemo } from "react";

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
  configSections = {},  // values from parsed config.ini sections
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
  const [configOverrides, setConfigOverrides] = useState([]);
  const baseSection = `${jobName}.config`;

  const sectionNames = useMemo(() => {
    const discoveredSections = Object.keys(configSections || {})
      .filter((section) => section.startsWith(`${jobName}.`) && section !== baseSection)
      .sort();
    return [baseSection, ...discoveredSections].filter(
      (section) => Object.keys(configSections?.[section] || {}).length > 0
    );
  }, [configSections, jobName, baseSection]);

  useEffect(() => {
    if (open) {
      const sectionValues = Object.fromEntries(
        sectionNames.map((section) => [section, { ...(configSections?.[section] || {}) }])
      );
      setValues(sectionValues);
      setOriginal(sectionValues);
    }
  }, [open, configSections, sectionNames]);

  const handleOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const handleFieldChange = (section, param) => (e) => {
    setValues((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] || {}),
        [param]: e.target.value,
      },
    }));
  };

  const handleReset = (section, param) => () => {
    setValues((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] || {}),
        [param]: original?.[section]?.[param],
      },
    }));
  };

  const handleStartToAutomationDialog = (e) => {
    e.preventDefault();
    const overrides = Object.entries(values).flatMap(([section, params]) =>
      Object.entries(params || {})
        .filter(([key, value]) => original?.[section]?.[key] !== value)
        .map(([key, value]) => [section, key, value])
    );
    setConfigOverrides(overrides);
    setOpen(false);
    setOpenChangeDialog(true);
  };

  const totalParameterCount = Object.values(values || {}).reduce(
    (count, sectionParams) => count + Object.keys(sectionParams || {}).length,
    0
  );

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
          {totalParameterCount === 0 && (
            <Typography variant="body2" component="p" color="textSecondary">No configuration parameters found for {jobName}.</Typography>
          )}

          {totalParameterCount > 0 && (
            <Typography variant="body2" component="span" gutterBottom>
              Override your default configuration parameters from sections starting with <code>[{jobName}.]</code>. These changes only apply to this run.
            </Typography>
          )}

          <form>
            {sectionNames.map((section) => {
              const sectionValues = values?.[section] || {};
              return (
                <FormControl component="fieldset" sx={{ mt: 4 }} key={section}>
                  <FormLabel component="legend" sx={{ mb: 1 }} >
                    <code>[{section}]</code>
                  </FormLabel>
                  <div>
                    {Object.entries(sectionValues).map(([param, value]) => {
                      const isModified = original?.[section]?.[param] !== value;
                      return (
                        <TextField
                          key={`${section}.${param}`}
                          label={param}
                          size="small"
                          autoComplete="off"
                          variant="outlined"
                          value={value}
                          onChange={handleFieldChange(section, param)}
                          InputLabelProps={{ shrink: true }}
                          InputProps={{
                            endAdornment: isModified && (
                              <InputAdornment position="end">
                                <IconButton size="small" aria-label={`Reset ${param}`} onClick={handleReset(section, param)}>
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
              );
            })}
          </form>
        </DialogContent>

        <DialogActions>
          <Button color="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleStartToAutomationDialog} disabled={totalParameterCount === 0}>
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
