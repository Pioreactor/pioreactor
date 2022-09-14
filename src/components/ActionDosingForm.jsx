import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import { makeStyles } from "@mui/styles";
import LoadingButton from '@mui/lab/LoadingButton';


const useStyles = makeStyles({
  actionTextField: {
    padding: "0px 10px 0px 0px",
    width: "175px",
  },
  actionForm: {
    padding: "20px 0px 0px 0px",
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
  const [isMLDisabled, setIsMLDisabled] = useState(false);
  const [isDurationDisabled, setIsDurationDisabled] = useState(false);
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [textfieldError, setTextfieldError] = useState(false);
  const [clicked, setClicked] = useState(false)

  const [formErrorDuration, setFormErrorDuration] = useState(false)
  const [formErrorML, setFormErrorML] = useState(false)


  function onSubmit(e) {
    e.preventDefault();
    if (mL !== EMPTYSTATE || duration !== EMPTYSTATE) {
      setClicked(true)
      const params = mL !== "" ? { ml: mL, source_of_event: "UI"} : { duration: duration, source_of_event: "UI"};
      fetch(`/run/${props.action}/${props.unit}`, {
        method: "POST",
        body: JSON.stringify(params),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });
      setSnackbarMsg(actionToAct[props.action] + (duration !== EMPTYSTATE ? (" for " +  duration + " seconds.") : (" until " + mL + "mL is reached.")))
      setOpenSnackbar(true);
      setTimeout(() => setClicked(false), 2500)
    }
    else {
      setTextfieldError(true)
    }

  }

  function stopPump(e) {
    fetch(`/stop/${props.action}/${props.unit}`, {method: "POST"})
  }

  function runPumpContinuously(e) {
    fetch(`/run/${props.action}/${props.unit}`, {
      method: "POST",
      body: JSON.stringify({continuously: true, source_of_event: "UI"}),
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
    })
    setSnackbarMsg("Running pump continuously")
    setOpenSnackbar(true)
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  function handleMLChange(e) {
    const re = /^[0-9.\b]+$/;
    setTextfieldError(false)

    setIsDurationDisabled(true);
    if (e.target.value === EMPTYSTATE) {
      setIsDurationDisabled(false);
    }

    setML(e.target.value);

    if (e.target.value === EMPTYSTATE || re.test(e.target.value)) {
      setFormErrorML(false)
    }
    else {
      setFormErrorML(true)
    }
  }

  function handleDurationChange(e) {
    const re = /^[0-9.\b]+$/;
    setTextfieldError(false)

    setIsMLDisabled(true);
    if (e.target.value === EMPTYSTATE) {
      setIsMLDisabled(false);
    }

    setDuration(e.target.value);

    if (e.target.value === EMPTYSTATE || re.test(e.target.value)) {
      setFormErrorDuration(false)
    }
    else {
      setFormErrorDuration(true)
    }
  }
  return (
    <form id={props.action} className={classes.actionForm}>
      <TextField
        name="mL"
        autoComplete={"off"}
        error={formErrorML || textfieldError}
        value={mL}
        size="small"
        id={props.action + "_mL"}
        label="mL"
        variant="outlined"
        disabled={isMLDisabled}
        onChange={handleMLChange}
        className={classes.actionTextField}
      />
      <TextField
        name="duration"
        autoComplete={"off"}
        value={duration}
        error={formErrorDuration || textfieldError}
        size="small"
        id={props.action + "_duration"}
        label="seconds"
        variant="outlined"
        disabled={isDurationDisabled}
        onChange={handleDurationChange}
        className={classes.actionTextField}
      />
      <br />
      <br />
      <div style={{display: "flex", justifyContent: "space-between"}}>
        <LoadingButton
          loading={clicked && (props?.job?.state === "disconnected")}
          disabled={formErrorML || formErrorDuration || (props?.job?.state === "ready")}
          type="submit"
          variant="contained"
          size="small"
          color="primary"
          onClick={onSubmit}
        >
          {props.action.replace(/_/g, " ")}
        </LoadingButton>
        <div>
          <Button
            size="small"
            color="primary"
            disabled={(props?.job?.state === "ready")}
            onClick={runPumpContinuously}
          >
            Run continuously
          </Button>
          <Button
            size="small"
            color="secondary"
            onClick={stopPump}
          >
            Interrupt
          </Button>
        </div>
      </div>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key={"snackbar" + props.unit + props.action}
      />
    </form>
  );
}