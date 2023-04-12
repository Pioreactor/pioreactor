import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import { makeStyles } from "@mui/styles";
import LoadingButton from '@mui/lab/LoadingButton';
import Radio from '@mui/material/Radio';
import RadioGroup from '@mui/material/RadioGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import FormControl from '@mui/material/FormControl';
import InputAdornment from '@mui/material/InputAdornment';


const useStyles = makeStyles({
  actionTextField: {
    padding: "0px 10px 0px 0px",
    width: "140px",
  },
  actionForm: {
    padding: "10px 0px 0px 0px",
  }
});


const actionToAct = {
  "remove_waste": "Removing waste",
  "add_media": "Adding media",
  "add_alt_media": "Adding alt. media",

}

export default function ActionPumpForm(props) {
  const EMPTYSTATE = "";
  const classes = useStyles();
  const [mL, setML] = useState(EMPTYSTATE);
  const [duration, setDuration] = useState(EMPTYSTATE);
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [textfieldError, setTextfieldError] = useState(false);
  const [clicked, setClicked] = useState(false)
  const [dosingMethod, setDosingMethod] = useState("volume")

  const [formErrorDuration, setFormErrorDuration] = useState(false)
  const [formErrorML, setFormErrorML] = useState(false)


  function onSubmit(e) {
    e.preventDefault();
    if ((dosingMethod === "continuously") || (dosingMethod === 'volume' && mL !== EMPTYSTATE) || (dosingMethod === 'duration' && duration !== EMPTYSTATE)) {
      setClicked(true)

      var params = {}
      var msg = ""
      if (dosingMethod === 'volume'){
        params = { ml: parseFloat(mL), source_of_event: "UI"};
        msg = actionToAct[props.action] + (" until " + mL + "mL is reached.")
      } else if (dosingMethod === 'duration') {
        params = { duration: parseFloat(duration), source_of_event: "UI"}
        msg = actionToAct[props.action] + (" for " +  duration + " seconds.")
      } else {
        params = {continuously: true, source_of_event: "UI"}
        msg = actionToAct[props.action] + " continuously"
      }

      fetch(`/api/run/${props.unit}/${props.action}`, {
        method: "POST",
        body: JSON.stringify({options: params, args: []}),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });
      setSnackbarMsg(msg)
      setOpenSnackbar(true);
      setTimeout(() => setClicked(false), 2500)
    }
    else {
      setTextfieldError(true)
    }

  }

  function stopPump(e) {
    fetch(`/api/stop/${props.unit}/${props.action}`, {method: "POST"})
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
    <div id={props.action} className={classes.actionForm}>
      <FormControl>
        <RadioGroup
          aria-labelledby="how to dose"
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
              className={classes.actionTextField}
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
              className={classes.actionTextField}
              InputProps={{
                endAdornment: <InputAdornment position="end">s</InputAdornment>,
              }}
            />
          </div>
          <FormControlLabel value="continuously" control={<Radio />} label="Run continuously" />
        </RadioGroup>
      </FormControl>


      <div style={{display: "flex", marginTop: '5px'}}>
        <LoadingButton
          loading={clicked && (props?.job?.state === "disconnected")}
          disabled={(formErrorML && dosingMethod === 'volume') || (formErrorDuration && dosingMethod === 'duration') || (props?.job?.state === "ready")}
          type="submit"
          variant="contained"
          size="small"
          color="primary"
          onClick={onSubmit}
          style={{marginRight: '3px'}}
        >
          Start
        </LoadingButton>
        <Button
          size="small"
          color="secondary"
          disabled={(props?.job?.state !== "ready")}
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