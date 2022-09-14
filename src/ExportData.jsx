import React from "react";
import moment from "moment";

import Grid from '@mui/material/Grid';

import { makeStyles } from '@mui/styles';
import FormLabel from '@mui/material/FormLabel';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import FormGroup from '@mui/material/FormGroup';
import FormControlLabel from '@mui/material/FormControlLabel';
import Checkbox from '@mui/material/Checkbox';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {Typography} from '@mui/material';
import Select from '@mui/material/Select';
import Box from '@mui/material/Box';
import LoadingButton from "@mui/lab/LoadingButton";
import FileDownloadIcon from '@mui/icons-material/FileDownload';

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
  caption: {
    marginLeft: "30px",
    maxWidth: "650px"
  }
}));



function ExperimentSelection(props) {
  const classes = useStyles();

  const [experiments, setExperiments] = React.useState([{experiment: "<All experiments>"}])

  React.useEffect(() => {
    async function getData() {
       await fetch("/api/get_experiments")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExperiments(prevState => [ ...data, ...prevState])
        props.handleChange(data[0].experiment)
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
        <InputLabel id="expSelect" variant="standard"> Experiment </InputLabel>
        <Select
          native
          labelId="expSelect"
          variant="standard"
          value={props.ExperimentSelection}
          onChange={handleExperimentSelectionChange}
          inputProps={{
            name: 'experiment',
            id: 'experiment',
          }}
        >
          {experiments.map((v) => {
            return <option value={v.experiment}>{v.experiment +  (v.created_at ? ` (started ${moment(v.created_at).format("MMMM D, YYYY")})` : "")}</option>
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
        <FormLabel component="legend">Datasets</FormLabel>
        <FormGroup>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.pioreactor_unit_activity_data} onChange={props.handleChange} name="pioreactor_unit_activity_data" />}
            label="Pioreactor Unit Activity Data"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The time series of OD metrics, temperature, stirring rates, LED updates, and dosings.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.growth_rates} onChange={props.handleChange} name="growth_rates" />}
            label="Implied growth rate"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The time series of the calculated (implied) growth rate. Same data as presented in the "Implied growth rate" chart in the Experiment Overview.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.od_readings} onChange={props.handleChange} name="od_readings" />}
            label="Optical density"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The time series of readings provided by the sensors (transformed via a calibration curve, if available), the inputs for growth calculations and normalized optical densities. Same data as presented in the "Optical density" chart in the Experiment Overview.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.od_readings_filtered} onChange={props.handleChange} name="od_readings_filtered" />}
            label="Normalized optical density"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The time series of normalized optical densities. Same data as presented in the "Normalized optical density" chart in the Experiment Overview.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_readings} onChange={props.handleChange} name="temperature_readings" />}
            label="Temperature readings"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The time series of temperature readings from the Pioreactors. Same data as presented in the "Temperature of vials" chart in the Experiment Overview.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.experiments} onChange={props.handleChange} name="experiments" />}
            label="Experiment metadata"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The description and other metadata from the experiment.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.alt_media_fractions} onChange={props.handleChange} name="alt_media_fractions" />}
            label="Alternative media fraction"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            A time series of how much alternative media is in each Pioreactor. Same data as presented in the "Fraction of volume that is alternative media" chart in the Experiment Overview.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_events} onChange={props.handleChange} name="dosing_events" />}
            label="Dosing event log"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            A detailed log table of all dosing events, including the volume exchanged, and the source of who or what triggered the event.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_events} onChange={props.handleChange} name="led_events" />}
            label="LED event log"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            A detailed log table of all LED events, including the channel, intensity, and the source of who or what triggered the event.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_automation_settings} onChange={props.handleChange} name="dosing_automation_settings" />}
            label="Dosing automation changelog"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Whenever a dosing automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the dosing automation states
            from this dataset.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_automation_settings} onChange={props.handleChange} name="led_automation_settings" />}
            label="LED automation changelog"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Whenever a LED automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the LED automation states
            from this dataset.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_automation_settings} onChange={props.handleChange} name="temperature_automation_settings" />}
            label="Temperature automation changelog"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Whenever a temperature automation is updated (new automation, new setting, etc.), a new row is recorded. You can reconstruct all the temperature automation states
            from this dataset.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.dosing_automation_events} onChange={props.handleChange} name="dosing_automation_events" />}
            label="Dosing automation events"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Log of automation events created by dosing automations.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.led_automation_events} onChange={props.handleChange} name="led_automation_events" />}
            label="LED automation events"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Log of automation events created by LED automations.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.temperature_automation_events} onChange={props.handleChange} name="temperature_automation_events" />}
            label="Temperature automation events"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Log of automation events created by temperature automations.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.kalman_filter_outputs} onChange={props.handleChange} name="kalman_filter_outputs" />}
            label="Kalman filter outputs"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            An internal Kalman filter produces the normalized optical densities, growth rates, an acceleration term, and variances (and covariances) between the estimates.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.stirring_rates} onChange={props.handleChange} name="stirring_rates" />}
            label="Stirring rates"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The measured RPM of the onboard stirring.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.pioreactor_unit_labels} onChange={props.handleChange} name="pioreactor_unit_labels" />}
            label="Pioreactor unit labels"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            Labels assigned to a Pioreactor during an experiment.
          </Typography>

          <FormControlLabel
            control={<Checkbox checked={props.isChecked.logs} onChange={props.handleChange} name="logs" />}
            label="Pioreactor logs"
          />
          <Typography variant="caption" className={classes.caption} gutterBottom>
            The append-only collection of logs from all Pioreactors. A subset of the these logs are displayed in the Log Table in the Experiment Overview.
            These are the logs that should be provided to get assistance when troubleshooting, but choose "&lt;All experiments&gt;" above.
          </Typography>

        </FormGroup>
      </FormControl>
    </div>
)}


function ExportDataContainer() {
  const classes = useStyles();
  const [isRunning, setIsRunning] = React.useState(false)
  const [isError, setIsError] = React.useState(false)
  const [errorMsg, setErrorMsg] = React.useState("")
  const [state, setState] = React.useState({
    experimentSelection: "",
    datasetCheckbox: {
      pioreactor_unit_activity_data: false,
      growth_rates: false,
      dosing_events: false,
      led_events: false,
      experiments: false,
      od_readings: false,
      od_readings_filtered: false,
      logs: false,
      alt_media_fraction: false,
      dosing_automation_settings: false,
      led_automation_settings: false,
      temperature_automation_settings: false,
      kalman_filter_outputs: false,
      stirring_rates: false,
      temperature_readings: false,
      pioreactor_unit_labels: false,
      led_automation_events: false,
      dosing_automation_events: false,
      temperature_automation_events: false,
    }
  });

  const onSubmit =  (event) => {
    event.preventDefault()

    if (!Object.values(state['datasetCheckbox']).some((e) => e)) {
      setIsError(true)
      setErrorMsg("At least one dataset must be selected.")
      return
    }

    setIsRunning(true)
    fetch('export_datasets',{
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
    });
  }

  const handleCheckboxChange = (event) => {
    setState(prevState => ({
      ...prevState,
      datasetCheckbox: {...state.datasetCheckbox, [event.target.name]: event.target.checked }
    }));
  };

  function handleExperimentSelectionChange(value) {
    setState(prevState => ({
      ...prevState,
      experimentSelection: value
    }));
  };

  const errorFeedbackOrDefault = isError ? <Box color="error.main">{errorMsg}</Box>: ""
  return (
    <React.Fragment>
      <div>
        <div>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Export Experiment Data
            </Box>
          </Typography>
        </div>

      </div>
      <Card className={classes.root}>

        <CardContent className={classes.cardContent}>
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
                <LoadingButton
                  type="submit"
                  variant="contained"
                  color="primary"
                  loading={isRunning}
                  loadingPosition="end"
                  onClick={onSubmit}
                  style={{width: "120px", marginLeft: 24}}
                  endIcon={<FileDownloadIcon />}
                >
                  Export
                </LoadingButton>
                <p style={{marginLeft: 24}}>{errorFeedbackOrDefault}</p>

              </Grid>
              <Grid item xs={12}>
                <p style={{textAlign: "center", marginTop: "30px"}}><span role="img" aria-labelledby="Note">💡</span> Learn more about <a href="https://docs.pioreactor.com/user-guide/export-data" target="_blank" rel="noopener noreferrer">data exporting</a>.</p>
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

