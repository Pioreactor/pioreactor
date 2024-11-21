import React from "react";
import dayjs from "dayjs";

import Grid from '@mui/material/Grid';
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
import { useTheme } from '@mui/material/styles';
import OutlinedInput from '@mui/material/OutlinedInput';
import Chip from '@mui/material/Chip';

const datasetDescription = {
    marginLeft: "30px",
    fontSize: 14,
    maxWidth: "80%",
}

function getStyles(value, values, theme) {
  return {
    fontWeight: values.includes(value)
      ? theme.typography.fontWeightMedium
      : theme.typography.fontWeightRegular,
  };
}

function MultipleSelectChip({availableValues, parentHandleChange}) {
  const theme = useTheme();
  const [values, setValues] = React.useState([]);

  const handleChange = (event) => {
    const {
      target: { value },
    } = event;
    if (value.includes("<All experiments>")){
      setValues(["<All experiments>"]);
      parentHandleChange(["<All experiments>"])
    }
    else {
      setValues(value);
      parentHandleChange(value)
    }
  };

  return (
    <div>
      <FormControl fullWidth variant="standard" component="fieldset" sx={{ maxWidth: 470 }}>
        <Typography variant="h6">Experiments</Typography>
        <Select
          labelId="expSelect"
          variant="standard"
          multiple
          value={values}
          onChange={handleChange}
          renderValue={(selected) => (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
              {selected.map((value) => (
                <Chip key={value} label={value} />
              ))}
            </Box>
          )}
          MenuProps={{ PaperProps: {
          style: {
              maxHeight: 250,
            },
          }}}
        >
          {availableValues.map((value) => (
            <MenuItem
              key={value}
              value={value}
              style={getStyles(value, values, theme)}
            >
              {value}
            </MenuItem>
          ))}
        </Select>
      </FormControl>
    </div>
  );
}


function ExperimentSelection(props) {

  const [experiments, setExperiments] = React.useState([])

  React.useEffect(() => {
    async function getData() {
      try {
        const response = await fetch("/api/experiments");
        const data = await response.json();
        const experimentNames = data.map((e) => e.experiment);

        // Ensure "<All experiments>" is always at the top
        setExperiments([...experimentNames, "<All experiments>"]);
      } catch (error) {
        console.error("Failed to fetch experiments:", error);
      }
    }

    getData();
  }, []);


  return (
    <Box sx={{ m: 1}}>
      <MultipleSelectChip availableValues={experiments} parentHandleChange={props.handleChange} />
    </Box>
  )
}

const PartitionBySelection = (props) => {
  return (
    <Box sx={{mt: 1}}>
      <FormControl component="fieldset" >
        <Box>
          <FormControlLabel
            control={<Checkbox checked={props.partitionByExperimentSelection} onChange={props.handleChange} name="partition_by_experiment" />}
            label="Partition output files by Experiment"
          /><br/>
          <FormControlLabel
            control={<Checkbox checked={props.partitionByUnitSelection} onChange={props.handleChange} name="partition_by_unit" />}
            label="Partition output files by Pioreactor unit"
          />
        </Box>
      </FormControl>
    </Box>
)}



const CheckboxesGroup = (props) => {

  return (
    <Box sx={{m: 1}}>
      <FormControl component="fieldset" >
        <Typography variant="h6">Available datasets</Typography>
        <FormGroup>

        {props.datasets.map( (dataset) => (
          <Box sx={{ml: 1, mt: 1}} key={dataset.dataset_name}>
            <FormControlLabel
              control={<Checkbox checked={props.selectedDatasets.includes(dataset.dataset_name)} onChange={props.handleChange} name={dataset.dataset_name} />}
              label={dataset.display_name}
            />
            {dataset.source !== "app"  &&
              <Typography  sx={{marginLeft: "30px"}} variant="caption" display="block" gutterBottom color="textSecondary">
              {`Provided by ${dataset.source}`}
              </Typography>
            }
            <Typography  sx={datasetDescription}>
              {dataset.description}
            </Typography>
          </Box>
        ))}

        </FormGroup>
      </FormControl>
    </Box>
)}


function ExportDataContainer() {
  const [isRunning, setIsRunning] = React.useState(false)
  const [isError, setIsError] = React.useState(false)
  const [errorMsg, setErrorMsg] = React.useState("")
  const [datasets, setDatasets] = React.useState([])

  const [state, setState] = React.useState({
    experimentSelection: [],
    partitionByUnitSelection: false,
    partitionByExperimentSelection: true,
    selectedDatasets: []
  });


  React.useEffect(() => {

    async function getDatasets() {
       await fetch("/api/contrib/exportable_datasets")
      .then((response) => {
        return response.json();
      })
      .then((data) => {
        setDatasets(data)
      });
    }
    getDatasets()
  }, [])


  const count = () => state.selectedDatasets.length

  const onSubmit =  (event) => {
    event.preventDefault()

    if (count() == 0) {
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
    const { name, checked } = event.target;

    setState((prevState) => {
      const updatedSelectedDatasets = [...prevState.selectedDatasets]; // Create a copy of the list

      if (checked) {
        if (!updatedSelectedDatasets.includes(name)) {
          updatedSelectedDatasets.push(name); // Add the item if not already in the list
        }
      } else {
        // Remove the item if unchecked
        const index = updatedSelectedDatasets.indexOf(name);
        if (index > -1) {
          updatedSelectedDatasets.splice(index, 1); // Remove the item
        }
      }

      return {
        ...prevState,
        selectedDatasets: updatedSelectedDatasets, // Update state with the new list
      };
    });
  };


  function handleExperimentSelectionChange(experiments) {
    console.log(experiments)
    setState(prevState => ({
      ...prevState,
      experimentSelection: experiments
    }));
  };

  function handlePartitionByChange(event) {
    switch (event.target.name) {
      case "partition_by_unit":
        setState(prevState => ({
          ...prevState,
          partitionByUnitSelection: event.target.checked
        }));
        break;
      case "partition_by_experiment":
        setState(prevState => ({
          ...prevState,
          partitionByExperimentSelection: event.target.checked
        }));
        break;
    }
  };

  const errorFeedbackOrDefault = isError ? <Box color="error.main">{errorMsg}</Box>: ""
  return (
    <React.Fragment>
      <Box>
        <Box sx={{display: "flex", justifyContent: "space-between", mb: 1}}>
          <Typography variant="h5" component="h2">
            <Box fontWeight="fontWeightBold">
              Export data
            </Box>
          </Typography>
          <Box sx={{display: "flex", flexDirection: "row", justifyContent: "flex-start", flexFlow: "wrap"}}>
            <LoadingButton
                type="submit"
                variant="contained"
                color="primary"
                loading={isRunning}
                loadingPosition="end"
                onClick={onSubmit}
                endIcon={<FileDownloadIcon />}
                disabled={count() === 0}
                style={{textTransform: 'none'}}
              >
                Export { count() > 0 ?  count() : ""}
            </LoadingButton>
          </Box>
        </Box>
      </Box>
      <Card >
        <CardContent sx={{p: 1}}>
          <p style={{marginLeft: 10}}>{errorFeedbackOrDefault}</p>

          <form>
            <Grid container spacing={0}>
              <Grid item xs={6} md={6}>
                <ExperimentSelection
                  experimentSelection={state.experimentSelection}
                  handleChange={handleExperimentSelectionChange}
                />
              </Grid>
              <Grid item xs={6} md={6}>
                <Typography variant="h6">Export options</Typography>
                <PartitionBySelection
                  partitionByUnitSelection={state.partitionByUnitSelection}
                  partitionByExperimentSelection={state.partitionByExperimentSelection}
                  handleChange={handlePartitionByChange}
                />
              </Grid>
              <Grid item xs={12} md={12}>
                <CheckboxesGroup
                selectedDatasets={state.selectedDatasets}
                handleChange={handleCheckboxChange}
                datasets={datasets}
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

