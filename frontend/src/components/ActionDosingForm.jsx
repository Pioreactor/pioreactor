import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from './Snackbar';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import InputAdornment from '@mui/material/InputAdornment';
import Alert from "@mui/material/Alert";
import {runPioreactorJob} from "../utilities"


const actionTextField = {
    padding: "0px 10px 0px 0px",
    width: "140px",
}

const actionToAct = {
  "remove_waste": "Removing waste",
  "add_media": "Adding media",
  "add_alt_media": "Adding alt. media",

}

export default function ActionPumpForm(props) {
  const { action, currentVolumeMl, experiment, job, thresholdMl, unit } = props;
  const EMPTYSTATE = "";
  const [mL, setML] = useState(EMPTYSTATE);
  const [duration, setDuration] = useState(EMPTYSTATE);
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [textfieldError, setTextfieldError] = useState(false);
  const [dosingMethod, setDosingMethod] = useState("volume")

  const [formErrorDuration, setFormErrorDuration] = useState(false)
  const [formErrorML, setFormErrorML] = useState(false)

  const parsedML = mL === EMPTYSTATE ? null : Number.parseFloat(mL);
  const isAddAction = action.startsWith("add")
  const isVolumeMode = dosingMethod === "volume";
  const isDurationMode = dosingMethod === "duration";
  const hasVolumeInput = mL !== EMPTYSTATE;
  const hasDurationInput = duration !== EMPTYSTATE;
  const hasSafetyThreshold = isAddAction && currentVolumeMl != null && thresholdMl != null;
  const hardRemainingMl = hasSafetyThreshold ? thresholdMl - currentVolumeMl : null;
  const exceedsSafetyThreshold = hasSafetyThreshold && isVolumeMode && parsedML != null && parsedML > hardRemainingMl;

  function onSubmit(e) {
    e.preventDefault();
    if (exceedsSafetyThreshold) {
      setTextfieldError(true)
      return
    }
    if (dosingMethod === "continuously" || (isVolumeMode && hasVolumeInput) || (isDurationMode && hasDurationInput)) {

      var params = {}
      var msg = ""
      if (isVolumeMode){
        params = { ml: parseFloat(mL), source_of_event: "UI"};
        msg = actionToAct[action] + (" until " + mL + "mL is reached.")
      } else if (isDurationMode) {
        params = { duration: parseFloat(duration), source_of_event: "UI"}
        msg = actionToAct[action] + (" for " +  duration + " seconds.")
      } else {
        params = {continuously: null, source_of_event: "UI"}
        msg = actionToAct[action] + " continuously"
      }

      runPioreactorJob(unit, experiment, action, [], params)
      setSnackbarMsg(msg)
      setOpenSnackbar(true);
    }
    else {
      setTextfieldError(true)
    }

  }

  function stopPump() {
    fetch(`/api/workers/${unit}/jobs/stop/job_name/${action}/experiments/${experiment}`, {method: "PATCH"})
    .catch(() => {
      setSnackbarMsg("🛑 Failed to stop - please try again!")
      setOpenSnackbar(true)
    });
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  function handleNumericChange(e, setValue, setError) {
    setTextfieldError(false)
    setValue(e.target.value);
    setError(e.target.value !== EMPTYSTATE && Number.isNaN(Number(e.target.value)))
  }

  function handleRadioChange(e) {
    setDosingMethod(e.target.value);
  }

  return (
    <div id={action} style={{padding: "10px 0px 0px 0px"}}>
      <FormControl>
        <RadioGroup
          aria-label="how to dose"
          name="how-to-dose-media"
          value={dosingMethod}
          onChange={handleRadioChange}
        >
          <div style={{marginBottom: "10px", maxWidth: "260px", display: "flex", justifyContent: "space-between"}}>
            <FormControlLabel value="volume" control={<Radio />} label="Volume" />
            <TextField
              name="mL"
              autoComplete={"off"}
              error={formErrorML || textfieldError}
              value={mL}
              size="small"
              id={action + "_mL"}
              variant="outlined"
              type="number"
              onChange={(e) => handleNumericChange(e, setML, setFormErrorML)}
              disabled={!isVolumeMode}
              sx={actionTextField}
              inputProps={{
                min: 0,
                step: 1,
                ...(hardRemainingMl != null ? { max: Math.max(hardRemainingMl, 0) } : {}),
              }}
              InputProps={{
                endAdornment: <InputAdornment position="end">mL</InputAdornment>,
              }}
            />
          </div>
          <div style={{marginBottom: "10px", maxWidth: "260px", display: "flex", justifyContent: "space-between"}}>
            <FormControlLabel value="duration" control={<Radio />} label="Duration" />
            <TextField
              name="duration"
              autoComplete={"off"}
              value={duration}
              error={formErrorDuration || textfieldError}
              size="small"
              id={action + "_duration"}
              variant="outlined"
              type="number"
              disabled={!isDurationMode}
              onChange={(e) => handleNumericChange(e, setDuration, setFormErrorDuration)}
              sx={actionTextField}
              InputProps={{
                endAdornment: <InputAdornment position="end">s</InputAdornment>,
              }}
            />
          </div>
          <FormControlLabel value="continuously" control={<Radio />} label="Run continuously" />
        </RadioGroup>
      </FormControl>


      <div style={{display: "flex", marginTop: '5px'}}>
        <Button
          disabled={(formErrorML && isVolumeMode) || (formErrorDuration && isDurationMode) || exceedsSafetyThreshold || (job?.state === "ready")}
          type="submit"
          variant="contained"
          size="small"
          color="primary"
          onClick={onSubmit}
          style={{marginRight: '10px'}}
        >
          Start
        </Button>
        <Button
          size="small"
          color="secondary"
          variant="contained"
          disabled={ (job?.state !== "ready") && (unit !== "$broadcast")} // always allow for "stop" in the "Manage all" dialog
          onClick={stopPump}
        >
          Stop
        </Button>
      </div>
      {isAddAction && exceedsSafetyThreshold && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          Entered volume exceeds the estimated headroom.
        </Alert>
      )}
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key={"snackbar" + unit + action}
      />
    </div>
  );
}
