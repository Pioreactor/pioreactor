import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import InputAdornment from '@mui/material/InputAdornment';
import {runPioreactorJob} from "../utilities"


const actionTextField = {
    padding: "0px 0px 0px 0px",
    width: "150px",
}



export default function ActionLEDForm(props) {
  const EMPTYSTATE = "";
  const re = /^[0-9.]+$/;
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [intensity, setIntensity] = useState(EMPTYSTATE);
  const [errorForm, setErrorForm] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const validInput = (intensity) => {
    if (intensity !== EMPTYSTATE && re.test(intensity)){
      if (parseFloat(intensity) >= 0 && parseFloat(intensity) <= 100){
        return true
      }
    }
    return false
  }

  function onSubmit(e) {
    if (validInput(intensity)) {
      setErrorForm(false)
      setIsSubmitted(true)
      setOpenSnackbar(true)

      const params = {[props.channel]: parseFloat(intensity), source_of_event: "UI"}
      runPioreactorJob(props.unit, props.experiment, "led_intensity", [], params)
    } else if (intensity === EMPTYSTATE) {
      setErrorForm(false)
    } else {
      setErrorForm(true)
    }
  }


  function onChange(e) {
    const proposedIntensity = e.target.value
    setIntensity(proposedIntensity)
    setIsSubmitted(false)
    if (validInput(proposedIntensity)) {
      setErrorForm(false)
    } else if (proposedIntensity === EMPTYSTATE) {
      setErrorForm(false)
    } else {
      setErrorForm(true)
    }
  }

  const handleSnackbarClose = (e, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    setOpenSnackbar(false);
  };


  const onKeyPress = (e) => {
      if ((e.key === "Enter") && (e.target.value)) {
        e.preventDefault()
        onSubmit()
    }
  }

  return (
    <form id={props.action} style={{padding: "10px 0px 0px 0px"}}>
      <div style={{display: "flex"}}>
        <TextField
          size="small"
          error={errorForm}
          name="intensity"
          autoComplete="off"
          value={intensity}
          id={props.channel + "_intensity_edit"}
          label="new intensity"
          variant="outlined"
          onChange={onChange}
          onKeyPress={onKeyPress}
          InputProps={{
            endAdornment: <InputAdornment position="end">%</InputAdornment>,
          }}
          sx={actionTextField}
        />
        <Button
          size="small"
          color="primary"
          onClick={onSubmit}
          disabled={(!validInput(intensity) || isSubmitted)}
          style={{marginLeft: "7px", textTransform: "none"}}
        >
          Update
        </Button>
      </div>
      <Snackbar
        anchorOrigin={{vertical: "bottom", horizontal: "center"}}
        open={openSnackbar}
        onClose={handleSnackbarClose}
        message={`Updating channel ${props.channel} to ${intensity}%.`}
        autoHideDuration={7000}
        key={"snackbar" + props.unit + props.channel}
      />
    </form>
  );
}
