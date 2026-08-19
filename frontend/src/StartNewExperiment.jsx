import React from "react";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';

import Autocomplete from '@mui/material/Autocomplete';
import Grid from '@mui/material/Grid';
import FormGroup from '@mui/material/FormGroup';
import Card from '@mui/material/Card';
import Box from '@mui/material/Box';
import CardContent from '@mui/material/CardContent';
import Chip from '@mui/material/Chip';
import {Typography} from '@mui/material';
import Button from "@mui/material/Button";
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import {useNavigate } from 'react-router';
import SaveIcon from '@mui/icons-material/Save';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import PlayCircleOutlinedIcon from '@mui/icons-material/PlayCircleOutlined';
import { useExperiment } from './providers/ExperimentContext';
import SelectButton from './components/SelectButton';

// Activate the UTC plugin
dayjs.extend(utc);


function normalizeTagList(tags) {
  const normalizedTags = [];
  const seenTags = new Set();

  for (const rawTag of tags) {
    if (typeof rawTag !== "string") {
      continue;
    }

    const tag = rawTag.trim();
    if (!tag) {
      continue;
    }

    const normalizedTag = tag.toLowerCase();
    if (seenTags.has(normalizedTag)) {
      continue;
    }

    normalizedTags.push(tag);
    seenTags.add(normalizedTag);
  }

  return normalizedTags;
}



function ExperimentSummaryForm(props) {
  const { allExperiments, updateExperiment } = useExperiment();
  const timestamp = dayjs.utc()
  const [formError, setFormError] = React.useState(false);
  const [helperText, setHelperText] = React.useState(" ");
  const [expName, setExpName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [tags, setTags] = React.useState([]);
  const [tagInputValue, setTagInputValue] = React.useState("");
  const [selectedPopulateExperimentName, setSelectedPopulateExperimentName] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const historicalExperimentList = allExperiments;
  const historicalExperiments = React.useMemo(
    () => historicalExperimentList.reduce((acc, {experiment}) => {
      acc[experiment] = 1;
      return acc;
    }, {}),
    [historicalExperimentList],
  );
  const tagOptions = React.useMemo(
    () => [...new Set(historicalExperimentList.flatMap(({tags = []}) => tags))]
      .filter((tag) => typeof tag === "string" && tag.trim())
      .sort((left, right) => left.localeCompare(right)),
    [historicalExperimentList],
  );
  const trimmedExpName = expName.trim();
  const hasInvalidCharacters = /[#$%+\/?\\]/.test(trimmedExpName);
  const nameAlreadyUsed = trimmedExpName in historicalExperiments;
  const hasBlockingValidationError = trimmedExpName === "" || hasInvalidCharacters || nameAlreadyUsed;
  const populateExperimentName = selectedPopulateExperimentName || historicalExperimentList[0]?.experiment || "";


  function populateFields(experimentName){
    const experimentToPopulate = historicalExperimentList.find(
      ({experiment}) => experiment === experimentName,
    );

    if (!experimentToPopulate) {
      return;
    }

    setExpName(experimentToPopulate.experiment)
    setDescription(experimentToPopulate.description ?? "")
    setTags(Array.isArray(experimentToPopulate.tags) ? experimentToPopulate.tags : [])
    setTagInputValue("")
  }


  async function onSubmit(e) {
    e.preventDefault();
    setLoading(true)

    if (trimmedExpName === ""){
      setFormError(true)
      setHelperText("Can't be blank.")
      setLoading(false)
      return
    }
    else if (hasInvalidCharacters) {
      setFormError(true)
      setHelperText("Can't use $, %, #, \\, /, + or ? characters in experiment name.")
      setLoading(false)
      return
    }

    const experimentMetadata = {
      experiment: trimmedExpName,
      created_at: timestamp.toISOString(),
      description: description,
      tags: normalizeTagList([...tags, tagInputValue]),
      delta_hours: 0,
      worker_count: 0,
    }

    try {
      const res = await fetch('/api/experiments', {
        method: "POST",
        body: JSON.stringify(experimentMetadata),
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      if (res.ok) {
        const savedExperiment = await res.json();
        setHelperText(" ")
        setFormError(false);
        updateExperiment(savedExperiment, true)
        props.handleNext()
        return
      }

      if (res.status === 409) {
        setFormError(true);
        setHelperText("Experiment name already used. Please choose another.")
        return
      }

      const json = await res.json().catch(() => null);
      setFormError(true);
      if (json && json.error) {
        setHelperText(`${json.error} Please retry.`);
      } else {
        setHelperText("Server error while creating experiment. Please retry or check system logs.");
      }
    } catch (_error) {
      setFormError(true);
      setHelperText("Network error while creating experiment. Check your connection and retry.");
    } finally {
      setLoading(false)
    }
  }

  const onExpNameChange = (e) => {
    var experimentNameProposed = e.target.value
    setExpName(experimentNameProposed)
    // realtime validation
    if (experimentNameProposed.trim() in historicalExperiments){
      setFormError(true);
      setHelperText("Experiment name already used. Please choose another.")
    }
    else if (/[#$%&+\/=?\\]/.test(experimentNameProposed)) {
      setFormError(true)
      setHelperText("Can't use $, %, #, &, \\, /, +, = or ? characters in experiment name.")
    }
    else {
      setHelperText(" ")
      setFormError(false)
    }
  }


  const onDescChange = (e) => {
    setDescription(e.target.value)
  }

  const commitPendingTag = React.useCallback(() => {
    if (!tagInputValue.trim()) {
      return;
    }

    setTags((previousTags) => normalizeTagList([...previousTags, tagInputValue]));
    setTagInputValue("");
  }, [tagInputValue]);

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
              label="Description (optional - can be edited later)"
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
              md: 12
            }}>
            <Autocomplete
              multiple
              freeSolo
              options={tagOptions}
              value={tags}
              inputValue={tagInputValue}
              onChange={(_event, nextTags) => setTags(normalizeTagList(nextTags))}
              onInputChange={(_event, nextValue, reason) => {
                if (reason === "reset") {
                  return;
                }
                setTagInputValue(nextValue);
              }}
              filterSelectedOptions
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Tags (optional - can be edited later)"
                  placeholder="Add a tag"
                  helperText="Press Enter or comma to add a tag."
                  onKeyDown={(event) => {
                    if ((event.key === "Enter" || event.key === ",") && tagInputValue.trim()) {
                      event.preventDefault();
                      commitPendingTag();
                    }
                  }}
                />
              )}
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
            <Box sx={{display: "flex", justifyContent: "flex-end"}}>
              {historicalExperimentList.length > 0 && (
                <Box sx={{mr: 1}}>
                  <SelectButton
                    variant="text"
                    color="primary"
                    value={populateExperimentName}
                    textPrefix={(
                      <React.Fragment>
                        <ContentCopyIcon fontSize="small" sx={{verticalAlign: "middle", m: "0px 3px"}} />
                        {"Populate from "}
                      </React.Fragment>
                    )}
                    renderValue={(experiment) => (
                      <Chip
                        component="span"
                        size="small"
                        icon={<PlayCircleOutlinedIcon />}
                        label={experiment}
                        data-experiment-name={experiment}
                        sx={{ml: 0.5, pointerEvents: "none"}}
                      />
                    )}
                    menuButtonAriaLabel="Choose a previous experiment"
                    onChange={({target: {value}}) => setSelectedPopulateExperimentName(value)}
                    onClick={({target: {value}}) => populateFields(value)}
                  >
                    {historicalExperimentList.map(({experiment}) => (
                      <MenuItem key={experiment} value={experiment}>{experiment}</MenuItem>
                    ))}
                  </SelectButton>
                </Box>
              )}
              <Button
                color="primary"
                variant="contained"
                onClick={onSubmit}
                endIcon={<SaveIcon />}
                sx={{textTransform: 'none'}}
                disabled={hasBlockingValidationError}
                loading={loading}
                loadingPosition="end"
              >
                Save
              </Button>
            </Box>
          </Grid>
        </Grid>
      </FormGroup>
    </Box>
  );
}



function StartNewExperimentContainer() {
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
