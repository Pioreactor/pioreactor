import React from "react";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import Grid from '@mui/material/Grid';
import FormGroup from '@mui/material/FormGroup';
import Card from '@mui/material/Card';
import Box from '@mui/material/Box';
import CardContent from '@mui/material/CardContent';
import {Typography} from '@mui/material';
import Button from "@mui/material/Button";
import TextField from '@mui/material/TextField';
import Autocomplete, { createFilterOptions } from '@mui/material/Autocomplete';
import {useNavigate } from 'react-router';
import SaveIcon from '@mui/icons-material/Save';
import LoadingButton from '@mui/lab/LoadingButton';

import { useExperiment } from './providers/ExperimentContext';

// Activate the UTC plugin
dayjs.extend(utc);



const filter = createFilterOptions();

function FreeSoloCreateOption(props) {
  const [value, setValue] = React.useState({key: props.value});
  const options = props.options
  const updateParentCallback = props.updateParentCallback

  React.useEffect( () => {
    setValue({key: props.value});
  }, [props.value]);

  return (
    <Autocomplete
      value={value}
      sx={{mt: 0, mb: 2, width: "100%"}}
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
      freeSolo
      renderInput={(params) => (
        <TextField {...params} label={props.label} />
      )}
    />
  );
}



function ExperimentSummaryForm(props) {
  const { updateExperiment } = useExperiment();
  const timestamp = dayjs.utc()
  const [formError, setFormError] = React.useState(false);
  const [helperText, setHelperText] = React.useState(" ");
  const [expName, setExpName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [organismUsed, setOrganismUsed] = React.useState("");
  const [mediaUsed, setMediaUsed] = React.useState("");
  const [historicalMediaUsed, setHistoricalMediaUsed] = React.useState([]);
  const [historicalOrganismUsed, setHistoricalOrganismUsed] = React.useState([]);
  const [historicalExperiments, setHistoricalExperiments] = React.useState({});
  const [loading, setLoading] = React.useState(false);

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


  function onSubmit(e) {
    e.preventDefault();
    setLoading(true)

    if (expName === ""){
      setFormError(true)
      setHelperText("Can't be blank.")
      setLoading(false)
      return
    }
    else if (expName.includes("#") || expName.includes("+") || expName.includes("/")|| expName.includes("$")|| expName.includes("%")|| expName.includes("\\")) {
      setFormError(true)
      setHelperText("Can't use $, %, #,\\, / or + characters in experiment name.")
      setLoading(false)
      return
    }

    const experimentMetadata = {experiment: expName.trim(), created_at: timestamp.toISOString(), description: description, mediaUsed: mediaUsed, organismUsed: organismUsed, delta_hours: 0}

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
          updateExperiment(experimentMetadata, true)
          props.handleNext()
        }
        else if (res.status === 409) {
          setFormError(true);
          setHelperText("Experiment name already used. Please choose another.")
        }
        else {
          res
            .json()
            .then((json) => {
               if (json && json.error) {
                setHelperText(json.error);
              } else {
                setHelperText("Server error. See UI logs.");
              }
            })
            .catch(() => {
              setHelperText("Server error. See UI logs.");
            });
          setFormError(true);
        }
        setLoading(false)
      })
  }

  const onExpNameChange = (e) => {
    var experimentNameProposed = e.target.value
    setExpName(experimentNameProposed)
    // realtime validation
    if (experimentNameProposed.trim() in historicalExperiments){
      setFormError(true);
      setHelperText("Experiment name already used. Please choose another.")
    }
    else if (experimentNameProposed.includes("#") || experimentNameProposed.includes("+") || experimentNameProposed.includes("/") ||experimentNameProposed.includes("$") ||experimentNameProposed.includes("%") || experimentNameProposed.includes("\\")) {
      setFormError(true)
      setHelperText("Can't use $, %, #, \\, / or + characters in experiment name.")
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
    <Box sx={{mt: "15px"}}>
      <FormGroup>
        <Grid container spacing={1}>
          <Grid
            size={{
              xs: 12,
              md: 8
            }}>
            <TextField
              error={formError}
              id="expName"
              label="Experiment name"
              value={expName}
              required
              sx={{mt: 0, mb: 0, width: "50%"}}
              onChange={onExpNameChange}
              helperText={helperText}
              />
          </Grid>
          <Grid
            size={{
              xs: 12,
              md: 6
            }}>
          </Grid>
          <Grid
            size={{
              xs: 12,
              md: 12
            }}>
            <TextField
              label="Description (optional)"
              rows={2}
              placeholder="Add a description. This description can be changed later."
              multiline
              value={description}
              sx={{mt: 0, mb: 2, width: "100%"}}
              onChange={onDescChange}
              fullWidth={true}
            />
          </Grid>

          <Grid
            size={{
              xs: 12,
              md: 6
            }}>
            <FreeSoloCreateOption
              options={historicalOrganismUsed}
              label="Organism / strain (optional)"
              updateParentCallback={setOrganismUsed}
              value={organismUsed}
            />
          </Grid>
          <Grid
            size={{
              xs: 12,
              md: 6
            }}>
            <FreeSoloCreateOption
              options={historicalMediaUsed}
              label="Media (optional)"
              updateParentCallback={setMediaUsed}
              value={mediaUsed}
            />
          </Grid>

          <Grid
            size={{
              xs: 12,
              md: 4
            }} />
          <Grid
            size={{
              xs: 12,
              md: 8
            }}>
            <Box style={{display: "flex", justifyContent: "flex-end"}}>
              <Button style={{marginRight: "10px", textTransform: "none"}} size="small" color="primary" onClick={populateFields}>Populate with previous experiment</Button>
              <LoadingButton
                color="primary"
                variant="contained"
                onClick={onSubmit}
                endIcon={<SaveIcon />}
                style={{textTransform: 'none'}}
                disabled={(expName==="") || formError}
                loading={loading}
                loadingPosition="end"
              >
                Save
              </LoadingButton>
            </Box>
          </Grid>
        </Grid>
      </FormGroup>
    </Box>
  );
}



function StartNewExperimentContainer(props) {
  const [activeStep, setActiveStep] = React.useState(0);
  const [skipped, setSkipped] = React.useState(new Set());
  const navigate = useNavigate();


  const getStepContent = (index) => {
    return steps[index].content
  }
  const isStepSkipped = (step) => {
    return skipped.has(step);
  };

  const handleNext = () => {
    if (activeStep === steps.length - 1){
      navigate('/overview') // change to location
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
    {title: 'Experiment summary', content: <ExperimentSummaryForm  handleNext={handleNext}/>, optional: false},
  ]


  return (
    <Card sx={{mt: "15px"}}>
      <CardContent sx={{p: 2}}>
        <Typography variant="h5" component="h1">
          Start a new experiment
        </Typography>
        <Box>
          <Box>
            <Box sx={{mt: 2, mb: 4, ml: "auto", mr: "auto", width: "70%"}}>{getStepContent(activeStep)}</Box>
            <Box>
            {(activeStep !== 0) && (
              <Box>
                <Button color="inherit" onClick={handleNext} sx={{ mr: 1, float: "right" }}>
                  Skip / Next
                </Button>
              </Box>
              )}
            </Box>
          </Box>
        </Box>
      </CardContent>
    </Card>
  )
}



function StartNewExperiment(props) {


  React.useEffect(() => {
    document.title = props.title;
  }, [props.title])
  return (
    <Grid container spacing={2} >
      <Grid
        size={{
          xs: 12,
          md: 12
        }}>
        <StartNewExperimentContainer />
      </Grid>
    </Grid>
  );
}

export default StartNewExperiment;
