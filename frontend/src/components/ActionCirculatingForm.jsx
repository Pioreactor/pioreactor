import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from './Snackbar';
import FormControl from '@mui/material/FormControl';
import InputAdornment from '@mui/material/InputAdornment';
import {runPioreactorJob} from "../utils/jobs"
import { experimentPathSegment } from "../utils/url";
import { Box } from "@mui/material";


const StyledTextField = {
  padding: "0px 10px 0px 0px",
  width: "140px",
}


const actionToAct = {
  "circulate_media": "Circulating media",
  "circulate_alt_media": "Circulating alt. media",

}

export default function ActionCirculatingForm(props) {
  const EMPTYSTATE = "";
  const [duration, setDuration] = useState(EMPTYSTATE);
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [snackbarMsg, setSnackbarMsg] = useState("");
  const [textfieldError, setTextfieldError] = useState(false);
  const [clicked, setClicked] = useState(false)

  const [formErrorDuration, setFormErrorDuration] = useState(false)


  function onSubmit(e) {
    e.preventDefault();
    if (duration !== EMPTYSTATE) {
      setClicked(true)

      var params = { duration: parseFloat(duration), source_of_event: "UI"}
      var msg = actionToAct[props.action] + (" for " +  duration + " seconds.")

      runPioreactorJob(props.unit, props.experiment, props.action, [], params)
      setSnackbarMsg(msg)
      setOpenSnackbar(true);
      setTimeout(() => setClicked(false), 2500)
    }
    else {
      setTextfieldError(true)
    }

  }

  function stopPump() {
    fetch(`/api/workers/${props.unit}/jobs/stop/job_name/${props.action}/experiments/${experimentPathSegment(props.experiment)}`, {method: "POST"})
    .catch(() => {
      setSnackbarMsg("🛑 Failed to stop - please try again!")
      setOpenSnackbar(true)
    });
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };


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
    <Box id={props.action} sx={{padding: "10px 0px 0px 0px"}}>
      <FormControl>
        <Box sx={{mb: "10px", maxWidth: "260px", display: "flex", justifyContent: "space-between"}}>
          <TextField
            name="duration"
            autoComplete={"off"}
            value={duration}
            error={formErrorDuration || textfieldError}
            size="small"
            sx={StyledTextField}
            id={props.action + "_duration"}
            variant="outlined"
            disabled={false}
            onChange={handleDurationChange}
            slotProps={{
              input: {
                endAdornment: <InputAdornment position="end">s</InputAdornment>,
              },
            }}
          />
        </Box>
      </FormControl>


      <br />
      <Box sx={{display: "flex"}}>
        <Button
          loading={clicked && (props?.job?.state === "disconnected")}
          disabled={formErrorDuration || (props?.job?.state === "ready")}
          type="submit"
          variant="contained"
          size="small"
          color="primary"
          onClick={onSubmit}
          sx={{mr: '10px'}}
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
      </Box>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={snackbarMsg}
        autoHideDuration={7000}
        key={"snackbar" + props.unit + props.action}
      />
    </Box>
  );
}
