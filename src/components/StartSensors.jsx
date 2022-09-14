import React from "react";
import Grid from '@mui/material/Grid';
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import Chart from "./Chart";
import ChangeAutomationsDialog from "./ChangeAutomationsDialog"
import CheckBoxOutlineBlankOutlinedIcon from '@mui/icons-material/CheckBoxOutlineBlankOutlined';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';

function StartHeating(props){

  const [isClicked, setIsClicked] = React.useState(false)
  const [openChangeTemperatureDialog, setOpenChangeTemperatureDialog] = React.useState(false);

  const onClick = () => {
    setOpenChangeTemperatureDialog(true);
    setIsClicked(true);
  };

  return(
    <div>
      <p> For consistent temperatures of the culture, we recommend using the onboard heating. Click below and set the temperature of the cultures (you can change this temperature later).</p>

      <Button
        variant="contained"
        onClick={onClick}
        endIcon={isClicked ? <CheckBoxOutlinedIcon/> : <CheckBoxOutlineBlankOutlinedIcon />}
      >
        Start heating
      </Button>

      <ChangeAutomationsDialog
        open={openChangeTemperatureDialog}
        onFinished={() => setOpenChangeTemperatureDialog(false)}
        unit="$broadcast"
        config={props.config}
        experiment="+"
        isJobRunning={false}
        automationType="temperature"
        no_skip_first_run={true}
      />

  </div>
  )
}


function StartStirring(props){

  const [isClicked, setIsClicked] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false);

  const onClick = (e) => {
    setIsClicked(true)
    fetch("/api/run/stirring/$broadcast", {
        method: "POST"}
      ).then(res => {
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
      <p> To get an accurate reading, we need to start start the stirring. This also provides gas transfer and keeps the cells in suspension.</p>
      <Button
        variant="contained"
        color="primary"
        endIcon={isClicked ? <CheckBoxOutlinedIcon/> : <CheckBoxOutlineBlankOutlinedIcon />}
        onClick={onClick}>
        Start stirring
      </Button>
      <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={openSnackbar}
      onClose={handleSnackbarClose}
      message="Stirring starting"
      autoHideDuration={7000}
      key="snackbarStirring"
    />
  </div>
  )
}


function StartODReading(props){

  const [isClicked, setIsClicked] = React.useState(false)
  const [openSnackbar, setOpenSnackbar] = React.useState(false);

  const onClick = (e) => {
    setIsClicked(true)
    fetch("/api/run/od_reading/$broadcast", {method: "POST"}).then(res => {
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
      <p> Next, we will turn on the optical density reading. We also call this <em>OD readings</em>. This will provide us with a measure of cell density. In a moment, you should see the data in the chart below. </p>
      <Button
        variant="contained"
        color="primary"
        endIcon={isClicked ? <CheckBoxOutlinedIcon/> : <CheckBoxOutlineBlankOutlinedIcon />}
        onClick={onClick}>
        Start OD readings
      </Button>
      <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={openSnackbar}
      onClose={handleSnackbarClose}
      message="OD reading starting"
      autoHideDuration={7000}
      key="snackbarOD"
    />
  </div>
  )
}


function StartSensors(props){
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
        <Grid item xs={10}><p>Place the vials in the Pioreactor(s).</p></Grid>
        <Grid item xs={10}><StartHeating config={props.config}/></Grid>
        <Grid item xs={10}><StartStirring/></Grid>
        <Grid item xs={10}><StartODReading/></Grid>
        <Grid item xs={12}>
          <Chart
            config={props.config}
            isODReading={true}
            dataSource="od_readings"
            title="Optical density"
            interpolation="stepAfter"
            topic="od_reading/od/+"
            yAxisLabel="Reading"
            payloadKey="od"
            experiment={null}
            deltaHours={1}
            lookback={1}
            fixedDecimals={3}
          />
        </Grid>
      </Grid>
      <Grid item xs={2}/>
    </Grid>
  );}


export default StartSensors;
