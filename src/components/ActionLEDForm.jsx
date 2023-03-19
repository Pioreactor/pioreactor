import React, {useState} from 'react'
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import { makeStyles } from "@mui/styles";
import InputAdornment from '@mui/material/InputAdornment';


const useStyles = makeStyles({
  actionTextField: {
    padding: "0px 0px 0px 0px",
    width: "150px",
  },
  actionForm: {
    padding: "10px 0px 0px 0px",
  }
});



export default function ActionLEDForm(props) {
  const EMPTYSTATE = "";
  const re = /^[0-9.\b]+$/;
  const classes = useStyles();
  const [openSnackbar, setOpenSnackbar] = useState(false);
  const [intensity, setIntensity] = useState(EMPTYSTATE);
  const [errorForm, setErrorForm] = useState(false);

  function onSubmit(e) {
    if (intensity !== EMPTYSTATE && re.test(intensity)) {
      setErrorForm(false)
      setOpenSnackbar(true);

      const params = {[props.channel]: parseFloat(intensity), source_of_event: "UI"}

      fetch(`/api/run/led_intensity/${props.unit}`, {
        method: "POST",
        body: JSON.stringify(params),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      }
      );
    } else {
      setErrorForm(true)
    }
  }


  function onChange(e) {
    setIntensity(e.target.value);
    if (e.target.value === EMPTYSTATE || re.test(e.target.value)) {
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
    <form id={props.action} className={classes.actionForm}>
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
          className={classes.actionTextField}
        />
        <Button
          size="small"
          color="primary"
          onClick={onSubmit}
          disabled={intensity === EMPTYSTATE}
          style={{marginLeft: "7px"}}
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