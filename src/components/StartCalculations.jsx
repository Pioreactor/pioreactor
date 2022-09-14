
import React from "react";
import Grid from '@mui/material/Grid';
import Button from "@mui/material/Button";
import Snackbar from "@mui/material/Snackbar";
import Chart from "./Chart";
import CheckBoxOutlineBlankOutlinedIcon from '@mui/icons-material/CheckBoxOutlineBlankOutlined';
import CheckBoxOutlinedIcon from '@mui/icons-material/CheckBoxOutlined';



function StartGrowthRate(props){

  const [openSnackbar, setOpenSnackbar] = React.useState(false);
  const [snackbarMessage, setSnackbarMessage] = React.useState("");
  const [isClicked, setIsClicked] = React.useState(false);

  const onClick = (e) => {
    fetch("/api/run/growth_rate_calculating/$broadcast", {method: "POST"}).then(r => {
      setSnackbarMessage("Growth rate calculating starting")
      setOpenSnackbar(true)
      setIsClicked(true)
    })
  }

  const handleSnackbarClose = () => {
    setOpenSnackbar(false);
  };

  return(
    <div>
      <p>Because of the varying strength & quality of the electronics, not all readings look the same - even for the same density of cells. So we compute a baseline measurement from the OD readings, and measure all growth against that baseline. </p>
      <p>From the (normalized) OD readings, we can calculate the <em>implied hourly growth rate</em>, which is our measure of growth. </p>
      <p>Let's start the growth rate calculations. This first computes the normalization constants, <b>which can take up to two minutes to complete</b>. After that, the graph below should start to populate.</p>
      <Button
        variant="contained"
        color="primary"
        endIcon={isClicked ? <CheckBoxOutlinedIcon/> : <CheckBoxOutlineBlankOutlinedIcon />}
        onClick={onClick}>
        Start growth rate calculations
      </Button>
      <Snackbar
      anchorOrigin={{vertical: "bottom", horizontal: "center"}}
      open={openSnackbar}
      onClose={handleSnackbarClose}
      message={snackbarMessage}
      autoHideDuration={7000}
      key={"snackbarGR"}
      />
  </div>
  )
}




function StartCalculations(props){
  const [experiment, setExperiment] = React.useState("null_exp")

  React.useEffect(() => {
    async function getData() {
         await fetch("/api/get_latest_experiment")
        .then((response) => {
          return response.json();
        })
        .then((data) => {
          setExperiment(data.experiment)
        });
      }
      getData()
  }, [])

  return (
    <Grid
      container
      direction="column"
      justifyContent="flex-start"
      alignItems="center"
      spacing={2}
    >
      <Grid item xs={2}/>
      <Grid item xs={10}><StartGrowthRate experiment={experiment}/></Grid>
      <Grid item xs={12}>
      <Chart
        config={props.config}
        experiment={experiment}
        dataSource="growth_rates"
        interpolation="stepAfter"
        title="Implied growth rate"
        topic="growth_rate_calculating/growth_rate"
        payloadKey="growth_rate"
        yAxisLabel="Growth rate, h⁻¹"
        yAxisDomain={[-0.02, 0.1]}
        lookback={100000}
        deltaHour={1}
        fixedDecimals={2}
      />
      </Grid>
      <Grid item xs={2}/>
    </Grid>
  );}


export default StartCalculations;
