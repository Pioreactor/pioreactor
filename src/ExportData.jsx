import React from "react";
import moment from "moment";

import Grid from '@mui/material/Grid';
import clsx from 'clsx';
import { makeStyles } from '@mui/styles';
import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import MenuItem from '@mui/material/MenuItem';
import {Typography} from '@mui/material';
import Select from '@mui/material/Select';
import Box from '@mui/material/Box';
import LoadingButton from "@mui/lab/LoadingButton";
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import { useSearchParams } from "react-router-dom";


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px",
  },
  title: {
    fontSize: 14,
  },
  cardContent: {
    padding: "10px"
  },
  pos: {
    marginBottom: 0,
  },
  datasetItem: {
    padding: "10px"
  },
  recommended: {
    backgroundColor: "rgba(83, 49, 202, 0.08)",
  },
  datasetDescription: {
    marginLeft: "30px",
    fontSize: 14
  },
  headerButtons: {display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"},
  headerMenu: {
    display: "flex",
    justifyContent: "space-between",
    marginBottom: "5px",
    [theme.breakpoints.down('lg')]:{
      flexFlow: "nowrap",
      flexDirection: "column",
    }
  },
}));



function ExperimentSelection(props) {
  const classes = useStyles();

  const [experiments, setExperiments] = React.useState([{experiment: "<All experiments>"}])

  React.useEffect(() => {
    async function getData() {
       await fetch("/api/experiments")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExperiments(prevState => [ ...data, ...prevState])
        if (props.experimentSelection === "") {
          props.handleChange(data[0].experiment)
        }
        else if (data.filter(e => e.experiment === props.experimentSelection).length === 0) {
          props.handleChange(data[0].experiment)
        }
      });
    }
    getData()
  }, [])

  const handleExperimentSelectionChange = (e) => {
    props.handleChange(e.target.value)
  }
  return (
    <div style={{maxWidth: "450px", margin: "10px"}}>
      <FormControl fullWidth component="fieldset" className={classes.formControl}>
        <FormLabel component="legend">Experiment</FormLabel>
        <Select
          labelId="expSelect"
          variant="standard"
          value={props.experimentSelection}
          onChange={handleExperimentSelectionChange}
        >
          {experiments.map((v) => {
            return <MenuItem key={v.experiment} value={v.experiment}>{v.experiment +  (v.created_at ? ` (started ${moment(v.created_at).format("MMMM D, YYYY")})` : "")}</MenuItem>
            }
          )}
        </Select>
      </FormControl>
    </div>
  )
}



const CheckboxesGroup = (props) => {
  const classes = useStyles();

  return (
    <div className={classes.root} style={{margin: "10px"}}>
      <FormControl component="fieldset" className={classes.formControl}>
        <FormLabel component="legend">Available datasets</FormLabel>
        <FormGroup>
          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
              control={<Checkbox checked={props.isChecked.pioreactor_unit_activity_data} onChange={props.handleChange} name="pioreactor_unit_activity_data" />}
              label="Pioreactor unit activity data (recommended)"
            />
            <Typography className={classes.datasetDescription} gutterBottom>
              This dataset contains most of your experiment data, including the time series of OD metrics, temperature, stirring rates, LED updates, and dosings.
            </Typography>
          </div>



          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.logs} onChange={props.handleChange} name="logs" />}
            label="Pioreactor logs"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes the append-only collection of logs from all Pioreactors. A subset of the these logs are displayed in the Log Table in the Experiment Overview.
              These are the logs that should be provided to get assistance when troubleshooting, but choose "&lt;All experiments&gt;" above.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
              control={<Checkbox checked={props.isChecked.growth_rates} onChange={props.handleChange} name="growth_rates" />}
              label="Implied growth rate"
            />
            <Typography className={classes.datasetDescription} gutterBottom>
             This dataset includes a time series of the calculated (implied) growth rate. This data matches what's presented in the "Implied growth rate" chart in the Experiment Overview.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
              control={<Checkbox checked={props.isChecked.od_readings} onChange={props.handleChange} name="od_readings" />}
              label="Optical density"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a time series of readings provided by the sensors (transformed via a calibration curve, if available), the inputs for growth calculations and normalized optical densities. This data matches what's presented in the "Optical density" chart in the Experiment Overview.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.od_readings_filtered} onChange={props.handleChange} name="od_readings_filtered" />}
            label="Normalized optical density"
          />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a time series of normalized optical densities. This data matches what's presented in the "Normalized optical density" chart in the Experiment Overview.
            </Typography>
          </div>
          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_readings} onChange={props.handleChange} name="temperature_readings" />}
            label="Temperature readings"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a time series of temperature readings from the Pioreactors. This data matches what's presented in the "Temperature of vials" chart in the Experiment Overview.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.experiments} onChange={props.handleChange} name="experiments" />}
            label="Experiment metadata"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes your experiment description and metadata.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.alt_media_fractions} onChange={props.handleChange} name="alt_media_fractions" />}
            label="Alternative media fraction"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a time series of how much alternative media is in each Pioreactor. This data matches what's presented in the "Fraction of volume that is alternative media" chart in the Experiment Overview.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
              <FormControlLabel
              control={<Checkbox checked={props.isChecked.pioreactor_unit_activity_data_rollup} onChange={props.handleChange} name="pioreactor_unit_activity_data_rollup" />}
              label="Pioreactor unit activity data roll-up"
            />
            <Typography className={classes.datasetDescription} gutterBottom>
              This dataset is a rolled-up version of Pioreactor unit activity data (above) aggregated to the minute level. This is useful for reducing the size of the exported dataset.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_events} onChange={props.handleChange} name="dosing_events" />}
            label="Dosing event log"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              In this dataset, you'll find a detailed log table of all dosing events, including the volume exchanged, and the source of who or what triggered the event.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_change_events} onChange={props.handleChange} name="led_change_events" />}
            label="LED event log"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              In this dataset, you'll find a log table of all LED events, including the channel, intensity, and the source of who or what triggered the event.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_automation_settings} onChange={props.handleChange} name="dosing_automation_settings" />}
            label="Dosing automation changelog"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              Anytime an automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the dosing automation states
              from this dataset.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_automation_settings} onChange={props.handleChange} name="led_automation_settings" />}
            label="LED automation changelog"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              Whenever a LED automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the LED automation states
              from this dataset.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_automation_settings} onChange={props.handleChange} name="temperature_automation_settings" />}
            label="Temperature automation changelog"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              Whenever a temperature automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the temperature automation states
              from this dataset.
            </Typography>
          </div>
          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_automation_events} onChange={props.handleChange} name="dosing_automation_events" />}
            label="Dosing automation events"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a log of automation events created by dosing automations.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_automation_events} onChange={props.handleChange} name="led_automation_events" />}
            label="LED automation events"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a log of automation events created by LED automations.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_automation_events} onChange={props.handleChange} name="temperature_automation_events" />}
            label="Temperature automation events"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a log of automation events created by temperature automations.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.kalman_filter_outputs} onChange={props.handleChange} name="kalman_filter_outputs" />}
            label="Kalman filter outputs"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset includes a time series of the internal Kalman filter. The Kalman filter produces the normalized optical densities, growth rates, an acceleration term, and variances (and covariances) between the estimates.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.stirring_rates} onChange={props.handleChange} name="stirring_rates" />}
            label="Stirring rates"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dowload includes the measured RPM of the onboard stirring.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.pioreactor_unit_labels} onChange={props.handleChange} name="pioreactor_unit_labels" />}
            label="Pioreactor unit labels"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              In this dataset, you'll find the labels assigned to a Pioreactor during an experiment.
            </Typography>
          </div>


          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.pwm_dcs} onChange={props.handleChange} name="pwm_dcs" />}
            label="PWM duty cycles"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset contains a time series of the PWMs duty cycle percentages. Useful for debugging PWM use.
            </Typography>
          </div>

          <div className={clsx(classes.datasetItem)}>
            <FormControlLabel
            control={<Checkbox checked={props.isChecked.ir_led_intensities} onChange={props.handleChange} name="ir_led_intensities" />}
            label="IR LED intensities"
            />
            <Typography  className={classes.datasetDescription} gutterBottom>
              This dataset contains a time series of the relative IR intensities used to normalized OD readings. Useful for debugging OD readings.
            </Typography>
          </div>

        </FormGroup>
      </FormControl>
    </div>
)}


function ExportDataContainer() {
  const [queryParams, setQueryParams] = useSearchParams();
  const classes = useStyles();
  const [isRunning, setIsRunning] = React.useState(false)
  const [isError, setIsError] = React.useState(false)
  const [errorMsg, setErrorMsg] = React.useState("")


  const [state, setState] = React.useState({
    experimentSelection: queryParams.get("experiment") || "",
    datasetCheckbox: {
      pioreactor_unit_activity_data: false || queryParams.get("pioreactor_unit_activity_data") === "1",
      growth_rates: false || queryParams.get("growth_rates") === "1",
      dosing_events: false || queryParams.get("dosing_events") === "1",
      led_change_events: false || queryParams.get("led_change_events") === "1",
      experiments: false || queryParams.get("experiments") === "1",
      od_readings: false || queryParams.get("od_readings") === "1",
      od_readings_filtered: false || queryParams.get("od_readings_filtered") === "1",
      logs: false || queryParams.get("logs") === "1",
      alt_media_fractions: false || queryParams.get("alt_media_fractions") === "1",
      dosing_automation_settings: false || queryParams.get("dosing_automation_settings") === "1",
      led_automation_settings: false || queryParams.get("led_automation_settings") === "1",
      temperature_automation_settings: false || queryParams.get("temperature_automation_settings") === "1",
      kalman_filter_outputs: false || queryParams.get("kalman_filter_outputs") === "1",
      stirring_rates: false || queryParams.get("stirring_rates") === "1",
      temperature_readings: false || queryParams.get("temperature_readings") === "1",
      pioreactor_unit_labels: false || queryParams.get("pioreactor_unit_labels") === "1",
      led_automation_events: false || queryParams.get("led_automation_events") === "1",
      dosing_automation_events: false || queryParams.get("dosing_automation_events") === "1",
      temperature_automation_events: false || queryParams.get("temperature_automation_events") === "1",
      pwm_dcs: false || queryParams.get("pwm_dcs") === "1",
      ir_led_intensities: false || queryParams.get("ir_led_intensities") === "1",
      pioreactor_unit_activity_data_rollup: false || queryParams.get("pioreactor_unit_activity_data_rollup") === "1",
    }
  });

  const count = () => Object.values(state.datasetCheckbox).reduce((acc, checked) => acc + (checked === true ? 1 : 0), 0);

  const onSubmit =  (event) => {
    event.preventDefault()

    if (!Object.values(state['datasetCheckbox']).some((e) => e)) {
      setIsError(true)
      setErrorMsg("At least one dataset must be selected.")
      return
    }

    setIsRunning(true)
    setErrorMsg("")
    fetch('/api/export_datasets',{
        method: "POST",
        body: JSON.stringify(state),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        },
    }).then(res => res.json())
      .then(res => {
      var link = document.createElement("a");
      const filename = res['filename'].replace(/%/g, "%25")
      link.setAttribute('export', filename);
      link.href = "/static/exports/" + filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setIsRunning(false)
    }).catch(e => {
      setIsRunning(false)
      setIsError(true)
      setErrorMsg("Server error occurred. Check logs.")
      console.log(e)
    });
  }

  const handleCheckboxChange = (event) => {
    setState(prevState => ({
      ...prevState,
      datasetCheckbox: {...state.datasetCheckbox, [event.target.name]: event.target.checked }
    }));
  };

  function handleExperimentSelectionChange(experimentName) {
    setState(prevState => ({
      ...prevState,
      experimentSelection: experimentName
    }));
  };

  const errorFeedbackOrDefault = isError ? <Box color="error.main">{errorMsg}</Box>: ""
  return (
    <React.Fragment>
      <div>
        <div className={classes.headerMenu}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Export Experiment Data
            </Box>
          </Typography>
          <div className={classes.headerButtons}>
            <LoadingButton
                type="submit"
                variant="contained"
                color="primary"
                loading={isRunning}
                loadingPosition="end"
                onClick={onSubmit}
                endIcon={<FileDownloadIcon />}
                disabled={count() === 0}
              >
                Export { count() > 0 ?  count() : ""}
            </LoadingButton>
          </div>
        </div>
      </div>
      <Card className={classes.root}>

        <CardContent className={classes.cardContent}>
          <p style={{marginLeft: 10}}>{errorFeedbackOrDefault}</p>

          <form>
            <Grid container spacing={0}>
              <Grid item xs={12} md={12}>
                <ExperimentSelection
                  experimentSelection={state.experimentSelection}
                  handleChange={handleExperimentSelectionChange}
                />
              </Grid>
              <Grid item xs={12} md={12}>
                <CheckboxesGroup
                isChecked={state.datasetCheckbox}
                handleChange={handleCheckboxChange}
                />
              </Grid>

              <Grid item xs={0}/>
              <Grid item xs={12}>
                <p style={{textAlign: "center", marginTop: "30px"}}>Learn more about <a href="https://docs.pioreactor.com/user-guide/export-data" target="_blank" rel="noopener noreferrer">data exporting</a>.</p>
              </Grid>
            </Grid>
          </form>
        </CardContent>
      </Card>
  </React.Fragment>
  )
}


function ExportData(props) {
    React.useEffect(() => {
      document.title = props.title;
    }, [props.title]);
    return (
        <Grid container spacing={2} >
          <Grid item md={12} xs={12}>
            <ExportDataContainer/>
          </Grid>
        </Grid>
    )
}

export default ExportData;

