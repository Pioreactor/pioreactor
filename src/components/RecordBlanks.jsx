import React from "react";
import Grid from '@mui/material/Grid';
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import Chart from "./Chart";
import ChangeAutomationsDialog from "./ChangeAutomationsDialog"
import CheckBoxOutlineBlankOutlinedIcon from '@mui/icons-material/CheckBoxOutlineBlankOutlined';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';


function StartODBlank(props){

  const [isClicked, setIsClicked] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false);

  const onClick = (e) => {
    setIsClicked(true)
    fetch("/api/run/od_blank/$broadcast", {method: "POST"}).then(res => {
      if (res.status === 200){
        setOpenSnackbar(true);
      }
    })
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  return(
    <div>
      <p> Place the vial(s), with media, into the Pioreactor(s). Click "Start" below to being recording OD blanks. This should take less than 3 minutes. </p>
      <Button
        variant="contained"
        color="primary"
        onClick={onClick}>
        Record OD blanks
      </Button>
      <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={openSnackbar}
      onClose={handleSnackbarClose}
      message="Recording OD blanks"
      autoHideDuration={7000}
      key="snackbarOD"
    />
  </div>
  )
}


function RecordBlanks(props){
  return (
    <Grid
      container
      direction="column"
      justifyContent="flex-start"
      alignItems="center"
      spacing={2}
    >
      <Grid item xs={2}/>
      <Grid container>
        <Grid item xs={10}><p>To improve the growth rate calculations, it's advisable to record a blank of the vial with only the media present (pre-innoculation). This step is optional, but highly recommended if your media is naturally turbid.</p></Grid>
        <Grid item xs={10}><StartODBlank config={props.config}/></Grid>
      </Grid>
      <Grid item xs={2}/>
    </Grid>
  );}


export default RecordBlanks;
