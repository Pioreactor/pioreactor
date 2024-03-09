import React from "react";
import moment from "moment";

import Grid from '@mui/material/Grid';
import { makeStyles } from '@mui/styles';
import FormGroup from '@mui/material/FormGroup';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/Card';
import {Typography} from '@mui/material';
import Button from "@mui/material/Button";
import TextField from '@mui/material/TextField';
import Autocomplete, { createFilterOptions } from '@mui/material/Autocomplete';
import SaveIcon from '@mui/icons-material/Save';

//import CleaningScript from "./components/CleaningScript"
import AssignLabels from "./components/AssignLabels"
//import RunFromExperimentProfile from "./components/RunFromExperimentProfile"
//import StartSensors from "./components/StartSensors"
//import StartCalculations from "./components/StartCalculations"
import {getConfig} from "./utilities"
import { useExperiment } from './providers/ExperimentContext';


const useStyles = makeStyles((theme) => ({
  root: {
    marginTop: "15px"
  },
  cardContent: {
    padding: "10px"
  },
  skipButton: {
    marginRight: theme.spacing(1),
    float: "right",
  },
  instructions: {
    marginTop: theme.spacing(2),
    marginBottom: theme.spacing(4),
    marginLeft: "auto",
    marginRight: "auto",
    width: "60%"
  },
  textField:{
    marginTop: theme.spacing(0),
    marginBottom: theme.spacing(2),
    width: "100%"

  },
  thinTextField:{
    marginTop: theme.spacing(2),
    marginBottom: theme.spacing(0),
    width: "100%"
  },
  formControl: {
    margin: theme.spacing(3),
  },
}));


const filter = createFilterOptions();

function FreeSoloCreateOption(props) {
  const classes = useStyles();
  const [value, setValue] = React.useState({key: props.value});
  const options = props.options
  const updateParentCallback = props.updateParentCallback

  React.useEffect( () => {
    setValue({key: props.value});
  }, [props.value]);

  return (
    <Autocomplete
      value={value}
      className={classes.textField}
      onChange={(event, newValue) => {
        if (typeof newValue === 'string') {
          setValue({
            key: newValue,
          });
          updateParentCallback(newValue)

        } else if (newValue && newValue.inputValue) {
          // Create a new value from the user input
          setValue({
            key: newValue.inputValue,
          });
          updateParentCallback(newValue.inputValue)

        } else {
          setValue(newValue);
          updateParentCallback(newValue?.key)
        }
      }}
      filterOptions={(options, params) => {
        const filtered = filter(options, params);

        const { inputValue } = params;
        // Suggest the creation of a new value
        const isExisting = options.some((option) => inputValue === option.key);
        if ((inputValue !== '') && !isExisting) {
          filtered.push({
            inputValue,
            key: `Add "${inputValue}"`,
          });
        }
        return filtered;
      }}
      selectOnFocus
      clearOnBlur
      handleHomeEndKeys
      id="free-solo-with-text-addition"
      options={options}
      getOptionLabel={(option) => {
        // Value selected with enter, right from the input
        if (typeof option === 'string') {
          return option;
        }
        // Add "xxx" option created dynamically
        if (option.inputValue) {
          return option.inputValue;
        }
        if (option.key){
          return option.key;
        }
        return ""
      }}
      renderOption={(props, option) => <li {...props}>{option.key}</li>}
      sx={{ width: 300 }}
      freeSolo
      renderInput={(params) => (
        <TextField {...params} label={props.label} />
      )}
    />
  );
}



function ExperimentSummaryForm(props) {
  const classes = useStyles();
  const { updateExperiment } = useExperiment();
  const timestamp = moment.utc()
  const [formError, setFormError] = React.useState(false);
  const [helperText, setHelperText] = React.useState(" ");
  const [expName, setExpName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [organismUsed, setOrganismUsed] = React.useState("");
  const [mediaUsed, setMediaUsed] = React.useState("");
  const [historicalMediaUsed, setHistoricalMediaUsed] = React.useState([]);
  const [historicalOrganismUsed, setHistoricalOrganismUsed] = React.useState([]);
  const [historicalExperiments, setHistoricalExperiments] = React.useState({});

  React.useEffect(() => {
    function getHistoricalExperiments() {
      fetch("/api/experiments")
        .then((response) => {
          if (response.ok){
            return response.json();
          }
        }).then(json => json.reduce((acc, {experiment}) => {
              acc[experiment] = 1;
              return acc;
            }, {}))
        .then(data => setHistoricalExperiments(data))
    }


    function populateDropDowns() {
      fetch("/api/historical_media")
        .then((response) => {
            if (response.ok) {
              return response.json();
            }
          })
        .then(json => setHistoricalMediaUsed(json))

      fetch("/api/historical_organisms")
        .then((response) => {
            if (response.ok) {
              return response.json();
            }
          })
        .then(json => setHistoricalOrganismUsed(json))
    }
    populateDropDowns();
    getHistoricalExperiments();
  }, [])


  function populateFields(){
    fetch("/api/experiments/latest")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setExpName(data.experiment)
        setDescription(data.description)
        setOrganismUsed(data.organism_used)
        setMediaUsed(data.media_used)
      });
  }


  function killExistingJobs(){
     fetch('/api/stop_all', {method: "POST"})
  }

  function onSubmit(e) {
    e.preventDefault();
    if (expName === ""){
      setFormError(true)
      setHelperText("Can't be blank.")
      return
    }
    else if (expName.includes("#") || expName.includes("+") || expName.includes("/")) {
      setFormError(true)
      setHelperText("Can't use #, / or + characters in experiment name.")
      return
    }

    const experimentMetadata = {experiment : expName.trim(), created_at: timestamp.toISOString(), description: description, mediaUsed: mediaUsed, organismUsed: organismUsed}

    fetch('/api/experiments', {
        method: "POST",
        body: JSON.stringify(experimentMetadata),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      }).then(res => {
        if (res.ok){
          setHelperText(" ")
          setFormError(false);
          updateExperiment(experimentMetadata)
          killExistingJobs()
          props.handleNext()
        }
        else if (res.status === 409) {
          setFormError(true);
          setHelperText("Experiment name already used. Please choose another.")
        }
        else {
          setFormError(true);
          setHelperText("Sever error. See UI logs.")
        }
      }
     )
  }

  const onExpNameChange = (e) => {
    var experimentNameProposed = e.target.value
    setExpName(experimentNameProposed)
    // realtime validation
    if (experimentNameProposed.trim() in historicalExperiments){
      setFormError(true);
      setHelperText("Experiment name already used. Please choose another.")
    }
    else if (experimentNameProposed.includes("#") || experimentNameProposed.includes("+") || experimentNameProposed.includes("/")) {
      setFormError(true)
      setHelperText("Can't use #, / or + characters in experiment name.")
    }
    else {
      setHelperText(" ")
      setFormError(false)
    }
  }


  const onDescChange = (e) => {
    setDescription(e.target.value)
  }

  return (
    <div className={classes.root}>
      <FormGroup>
        <Grid container spacing={1}>
          <Grid item xs={12} md={8}>
            <TextField
              error={formError}
              id="expName"
              label="Experiment name"
              value={expName}
              required
              className={classes.thinTextField}
              onChange={onExpNameChange}
              helperText={helperText}
              />
          </Grid>
          <Grid item xs={12} md={6}>
          </Grid>
          <Grid item xs={12} md={12}>
            <TextField
              label="Description (optional)"
              rows={2}
              placeholder="Add a description. This description can be changed later."
              multiline
              value={description}
              className={classes.textField}
              onChange={onDescChange}
              fullWidth={true}
            />
          </Grid>

          <Grid item xs={12} md={6}>
            <FreeSoloCreateOption
              options={historicalOrganismUsed}
              label="Organism / strain (optional)"
              updateParentCallback={setOrganismUsed}
              value={organismUsed}
            />
          </Grid>
          <Grid item xs={12} md={6}>
            <FreeSoloCreateOption
              options={historicalMediaUsed}
              label="Media (optional)"
              updateParentCallback={setMediaUsed}
              value={mediaUsed}
            />
          </Grid>

          <Grid item xs={12} md={4}/>
          <Grid item xs={12} md={8}>
            <div style={{display: "flex", justifyContent: "flex-end"}}>
              <Button style={{marginRight: "10px", textTransform: "none"}} size="small" color="primary" onClick={populateFields}>Populate with previous experiment</Button>
              <Button
                variant="contained"
                color="primary"
                onClick={onSubmit}
                endIcon={<SaveIcon />}
                disabled={(expName==="") || formError}
              >
                Save
              </Button>
            </div>
          </Grid>
        </Grid>
      </FormGroup>
    </div>
  );
}





function StartNewExperimentContainer(props) {
  const classes = useStyles();
  const [activeStep, setActiveStep] = React.useState(0);
  const [skipped, setSkipped] = React.useState(new Set());
  const countActiveUnits = props.config['cluster.inventory'] ? Object.entries(props.config['cluster.inventory']).filter((v) => v[1] === "1").map((v) => v[0]).length : 0


  const getStepContent = (index) => {
    return steps[index].content
  }
  const isStepSkipped = (step) => {
    return skipped.has(step);
  };

  const handleNext = () => {
    if (activeStep === steps.length - 1){
      window.location.href = "/overview"; // change to location
    } else {

      let newSkipped = skipped;
      if (isStepSkipped(activeStep)) {
        newSkipped = new Set(newSkipped.values());
        newSkipped.delete(activeStep);
      }

      setActiveStep((prevActiveStep) => prevActiveStep + 1);
      setSkipped(newSkipped);
      window.scrollTo({top: 0})
    }
  };


  const steps = [
    {title: 'Experiment summary', content: <ExperimentSummaryForm config={props.config} handleNext={handleNext}/>, optional: false},
  ]

  if (countActiveUnits > 1){
    steps.push({title: 'Assign labels', content: <AssignLabels config={props.config} handleNext={handleNext} />, optional: true})
  }

  return (
    <Card className={classes.root}>
      <CardContent className={classes.cardContent}>
        <Typography variant="h5" component="h1">
          Start a new experiment
        </Typography>
        <div>
          <div>
            <div className={classes.instructions}>{getStepContent(activeStep)}</div>
            <div>
            {(activeStep !== 0) && (
              <div>
                <Button color="inherit" onClick={handleNext} sx={{ mr: 1 }} className={classes.skipButton}>
                  Skip / Next
                </Button>
              </div>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}



function StartNewExperiment(props) {
  const [config, setConfig] = React.useState({})

  React.useEffect(() => {
    getConfig(setConfig)
  }, [])

  React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
  return (
      <Grid container spacing={2} >
        <Grid item xs={12} md={12}>
          <StartNewExperimentContainer config={config}/>
        </Grid>
      </Grid>
  )
}

export default StartNewExperiment;

