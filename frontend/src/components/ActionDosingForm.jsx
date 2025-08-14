import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import InputAdornment from '@mui/material/InputAdornment';
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
  const EMPTYSTATE = "";
  const [mL, setML] = useState(EMPTYSTATE);
  const [duration, setDuration] = useState(EMPTYSTATE);
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [textfieldError, setTextfieldError] = useState(false);
  const [dosingMethod, setDosingMethod] = useState("volume")

  const [formErrorDuration, setFormErrorDuration] = useState(false)
  const [formErrorML, setFormErrorML] = useState(false)


  function onSubmit(e) {
    e.preventDefault();
    if ((dosingMethod === "continuously") || (dosingMethod === 'volume' && mL !== EMPTYSTATE) || (dosingMethod === 'duration' && duration !== EMPTYSTATE)) {

      var params = {}
      var msg = ""
      if (dosingMethod === 'volume'){
        params = { ml: parseFloat(mL), source_of_event: "UI"};
        msg = actionToAct[props.action] + (" until " + mL + "mL is reached.")
      } else if (dosingMethod === 'duration') {
        params = { duration: parseFloat(duration), source_of_event: "UI"}
        msg = actionToAct[props.action] + (" for " +  duration + " seconds.")
      } else {
        params = {continuously: null, source_of_event: "UI"}
        msg = actionToAct[props.action] + " continuously"
      }

      runPioreactorJob(props.unit, props.experiment, props.action, [], params)
      setSnackbarMsg(msg)
      setOpenSnackbar(true);
    }
    else {
      setTextfieldError(true)
    }

  }

  function stopPump(e) {
    fetch(`/api/workers/${props.unit}/jobs/stop/job_name/${props.action}/experiments/${props.experiment}`, {method: "PATCH"})
    .catch((error) => {
      setSnackbarMsg("🛑 Failed to stop - please try again!")
      setOpenSnackbar(true)
    });
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  function handleMLChange(e) {
    const re = /^[0-9.\b]+$/;
    setTextfieldError(false)

    setML(e.target.value);

    if (e.target.value === EMPTYSTATE || re.test(e.target.value)) {
      setFormErrorML(false)
    }
    else {
      setFormErrorML(true)
    }
  }

  function handleRadioChange(e) {
    setDosingMethod(e.target.value);
  }

  function handleDurationChange(e) {
    const re = /^[0-9.\b]+$/;
    setTextfieldError(false)

    setDuration(e.target.value);

    if (e.target.value === EMPTYSTATE || re.test(e.target.value)) {
      setFormErrorDuration(false)
    }
    else {
      setFormErrorDuration(true)
    }
  }
  return (
    <div id={props.action} style={{padding: "10px 0px 0px 0px"}}>
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
              id={props.action + "_mL"}
              variant="outlined"
              onChange={handleMLChange}
              disabled={dosingMethod !== 'volume'}
              sx={actionTextField}
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
              id={props.action + "_duration"}
              variant="outlined"
              disabled={dosingMethod !== 'duration'}
              onChange={handleDurationChange}
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
          disabled={(formErrorML && dosingMethod === 'volume') || (formErrorDuration && dosingMethod === 'duration') || (props?.job?.state === "ready")}
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
          disabled={ (props?.job?.state !== "ready") && (props.unit !== "$broadcast")} // always allow for "stop" in the "Manage all" dialog
          onClick={stopPump}
        >
          Stop
        </Button>
      </div>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key={"snackbar" + props.unit + props.action}
      />
    </div>
  );
}
